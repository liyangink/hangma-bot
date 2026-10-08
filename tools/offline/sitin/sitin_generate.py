"""坐隐 3.1：最小真实生成闭环脚手架（I1 初始化 / M1 修订 / 解析 / 隔离装载 / 血缘）。

## 1. 用途与依据

[PLAN-REVISION §3.1](../../PLAN-REVISION-2026-09-15.md)（配合 [README §17 第三步](../../README.md)
与 [DESIGN §3](../../DESIGN.md)）要求的最小闭环是**一次可复现的**
「构提示词 → 模型调用 → 解析 → 隔离装载 → 血缘落盘」：

- **I1 初始化**：接收任务、**允许信息**、函数合同、单位、限制与反例；
- **M1 修订**：再接收**父代**（含其绑定身份）与反馈；
- 借用 EoH 的固定统一输出格式（「机制说明 + 代码」），出处
  [LLM4AD@ffb6acf 的 prompt.py](https://github.com/Optima-CityU/LLM4AD/blob/ffb6acf64497be93932c98d25369352efd3865cf/llm4ad/method/eoh/prompt.py)：
  框内一句话＝思想，函数体＝代码，解析器据此切成 `(thought, code)`；
- 每次调用保存：算子、模型版本/采样设置、**提示词原文与哈希**、父代绑定身份、
  允许事实/代码清单、原始回复、解析结果、代码与其哈希、隔离装载结论、
  墙钟时间与单调耗时、消耗与重试。**不记录任何凭据。**

## 2. 本工具**不**做什么（边界，非常重要）

1. **没有自动上线通道。** 生成的候选只落到 `--out` 指定的离线目录，
   不写 `src/hangma_bot/policy/heuristics/`、不改静态注册表、不碰线上配置与默认策略。
   记录里恒有 `registration.registered=false` 与 `registration.auto_publish=false`。
2. **隔离装载 ≠ 三道门禁。** 本工具的装载阶段与门禁的 **G-0（受监管装载与构造）同级**：
   它只证明「语法可解析、入口存在、能在受监管子进程里构造出 `HeuristicAdjustment`、
   冷启动探针不抛异常」。它**不**替代 G-1（规则事实/时间纯度）、G-2（行为/退化诊断）、
   G-3（触发条件登记），所以记录里恒有 `load.equivalent_to_three_gates=false`
   与 `gates_run=[]`。**绝不能把「装载成功」读成「通过准入」。**
3. **准入前置条件未满足，且阻塞原因是"查出来的"。** 记录里恒有
   `admission.eligible=false`、`status="pending_admission"`、
   **`as_of_utc`** 与三项实际检查（注册表里有没有同一份源码、门禁记录有没有指向它、
   人工审核是否可机器核验）。**不写死"某步骤未收口"这类当时事实**：
   `unfreeze_path` 写明解冻路径，本轮**刻意不做解冻**。
4. **不做效果结论。** 本工具不跑桌赛、不产出适应度，也不把任何行为信号当强度证据。
5. **不训练任何模型、线上无 LLM 调用。** 只有离线的调用往返（或落盘夹具）。

## 3. 四个可插拔后端与三种回复来源

**后端只决定"这次回复从哪来"，不改变落盘血缘的形状**——四种后端产出的记录字段完全一致，
因此将来换通道不会让证据形状变化。

| 后端 | 做什么 | 本轮状态 |
| --- | --- | --- |
| `headless` | **默认通道**：把提示词交给一个 DSH 子进程（`dsh --profile headless`），**stdout = 答复**、**stderr = 推理过程（丢弃）**；子进程 cwd = mkdtemp、环境变量白名单 + 只注入 `DSH_HOME`/密钥；**模型身份从运行痕迹读**（`sessions/**/session.jsonl.zstd` 的 `request/header.config`）。信息边界**弱于** api（运行体具备工作区能力，靠提示词约束） | 本轮真跑 |
| `delegate` | **文件式交接**：`--emit-prompt` 产出提示词原文/哈希/允许面清单，交给上游去委派；拿到回复后用 `--ingest-reply <文件>` 走完解析→装载→血缘。**工具内部不调用任何外部代理**（Python 侧没有子代理 API，也不该有：工具若能自己造出一条"模型回复"，血缘里"谁产的"就说不清了） | 本轮真跑 |
| `replay` | 回放**已落盘**的回复，逐字节可复现（离线回归、换机复跑） | 回归主用 |
| `api` | OpenAI 兼容 HTTP，**真跑**：凭据按 `SITIN_LLM_CONFIG` → `DEEPSEEK_API_KEY` → `.private/sitin-llm.json` 解析（**绝不落盘**）；默认档位 `junior`（`deepseek-flash`）。**推理模型**：只取 `message.content`，`reasoning_content` 只记存在与长度；`finish_reason != "stop"` 视为**截断**，不得当合法回复解析 | 本轮实跑（见证据 README §5） |
**回复来源决定 `reply.evidence_kind`，并同时决定"取证强度"**
（`reply.provenance_attestation`，GL-9）：封套是**人填的**，没有签名也没有回执，
因此只能算"自述"；api 与 headless 是工具自己发出并观测到的。

| 取值 | 含义 | 文件里必须同时具备 | 取证强度 |
| --- | --- | --- | --- |
| `headless_model_reply` | headless 子进程 stdout | 无封套；身份从会话痕迹读 | `tool-observed-stdout-and-session-log` |
| `captured_model_reply` | 工具自己发 HTTP 拿到的回复 | `provider`/`model`/`captured_at_utc` | `tool-observed-http` |
| `delegated_model_reply` | 委派通道取回的回复 | 上述四项 + `delegator` | `envelope-self-declared` |
| `format_fixture` | **人工构造的格式夹具**（不是模型输出） | `author`/`purpose`，且**不得**带 provider/model | `human-authored-fixture` |

有封套的三种来源都必须让 `prompt_sha256` 与本次提示词**逐字节一致**，否则拒绝摄入
（不接受把另一次回复当作本次回复）。`format_fixture` 永远不是候选
（`is_model_output=false`、`admission.eligible=false`）。

### 3.1 生成端的两条硬事实（本机实测，写进工具以免后人重踩）

1. **`deepseek-flash` 是重推理模型，`max_tokens` 必须给足。** 实测：同一提示词下
   `max_tokens=4096` 与 `16384` 时预算被 `reasoning_tokens` 占满、正文为空、
   `finish_reason="length"`；`65536` 时才产出正文（思维链约 21.8K tokens，正文 8.6K 字符）。
   因此"给 4096 就够"是错的；截断回复会被判 `PARSE_TRUNCATED` 并进修复路径，**不会**被当成候选。
2. **凭据与采样**：凭据只经环境或私有配置进入传输层；采样参数只在**真的发出请求**（api 直连）时记录，
   并注明 `source="request_body"` 与取值来源。delegate/replay 通道不发生采样，`sampling` 记 `null`。

### 3.2 headless 通道的用量与身份都从**会话日志**读

`dsh --profile headless` 每次运行会在 `<DSH_HOME>/sessions/**/session.jsonl.zstd` 留下
完整痕迹，工具从同一个文件里读两样东西，因此 `identity_source=session_log` 与
`usage_source=session_log` **同源**：

| 读什么 | 事件 | 字段 |
| --- | --- | --- |
| 实际使用的模型身份 | `request/header` | `data.header.config`（provider / model / reasoningEffort / maxTokens） |
| 实际 token 用量 | `assistant/chunk` 且 `data.chunk.type == "usage"` | `data.chunk.usage`（inputTokens / outputTokens / totalTokens / cacheReadTokens / reasoningTokens），**多条累加** |

**为什么必须做**：用户给了明确的 token 预算并要按 token 报账；读不到用量，默认通道就是
"花多少看不见"，预算账本没法用。只有当日志里**确实没有** usage 事件时才回落
`tokens_unknown=true`。

## 4. 复跑

    # 只看提示词（不花钱、不写回复）
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py \
        i1 --out /tmp/sitin-gen-i1 --dry-run

    # 用落盘夹具（或模型实录）跑通 I1 / M1 全流程
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py \
        i1 --out review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation/run-i1 \
        --replay review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation/fixtures/i1-positive.json

    # 默认通道 headless（每次起一个 DSH 进程，时延明显高于直连 HTTP）
    ... i1 --out <DIR>                    # 缺省就是 --backend headless

    # 委派通道：先产出交接件，交给上游委派，再摄入回复
    ... i1 --out <DIR> --backend delegate --emit-prompt
    ... i1 --out <DIR> --backend delegate --ingest-reply <回复 JSON>

    # api 直连（可选通道；本轮也真跑过）
    ... i1 --out <DIR> --backend api --tier junior --max-tokens 131072

    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_generate.py -q

## 5. 证据分级（根 AGENTS.md §3）

- **官方已确认**：无（本工具不引入任何规则事实）。
- **当前观察**：本机与 `.venv` 下实跑的解析/装载/拒绝路径结论，落 `evidence/3.1-generation/`。
- **工程建议**：提示词结构、允许面清单、装载层级划分、预算与重试口径。
- **待确认假设**：模型能否稳定产出可装载候选；真实调用成本与成功率。
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
import ast
import dataclasses
import datetime
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: 仓库根：本文件位于 <root>/review/<route>/tools/sitin_generate.py。
REPO = _PROJECT_ROOT
SRC_ROOT = _project_file(_PROJECT_ROOT, REPO / "src")
_HERE = Path(__file__).resolve().parent
for _path in (str(SRC_ROOT), str(_HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _load_sibling(name: str):
    """按文件路径装载同目录工具（与门禁/调度器同一写法）。

    **为什么共享 `sitin_process`**：REVIEW-8 S8-2 的教训是"每处各写一份终止逻辑，
    就会有两份不同的缺陷"。生成端执行的是**任意离线代码**，与门禁同源，
    因此必须走同一个受监管入口，不另造一份。
    """

    module_path = _project_file(_PROJECT_ROOT, _HERE / (name + ".py"))
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


process_guard = _load_sibling("sitin_process")

# ---------------------------------------------------------------- schema 常量

#: 血缘记录 schema；字段只增不改语义，改语义必须换版本号。
GENERATION_RECORD_SCHEMA = "sitin-generation-record/1"
#: 隔离装载报告 schema。
LOAD_REPORT_SCHEMA = "sitin-generation-load/1"
#: 任务合同（提示词里的允许面）schema。
CONTRACT_SCHEMA = "sitin-generation-contract/1"
#: 落盘回复夹具 schema（`--replay`）。
REPLY_FILE_SCHEMA = "sitin-generation-reply/1"
#: 生成调用台账 schema（独立于日志落盘，与调度器台账同一纪律）。
BUDGET_SCHEMA = "sitin-generation-budget/1"

#: 提示词要求的入口函数名（候选装载接缝的唯一约定，见 policy/heuristics/__init__.py）。
ENTRY_NAME = "build_adjustment_from_params"

OPERATOR_I1 = "i1"
OPERATOR_M1 = "m1"
OPERATORS = (OPERATOR_I1, OPERATOR_M1)

#: 记录里的证据种类（见模块 docstring §3）；**由回复来源决定，不由调用方口头指定**。
REPLY_HEADLESS = "headless_model_reply"     # headless 子进程 stdout（真实模型答复）
REPLY_DELEGATED = "delegated_model_reply"   # 委派通道拿到的**真实**模型回复
REPLY_CAPTURED = "captured_model_reply"     # 工具自己 HTTP 调用拿到的真实模型回复
REPLY_FIXTURE = "format_fixture"            # 人工构造的格式夹具（**不是**模型输出）
REPLY_KINDS = (REPLY_HEADLESS, REPLY_DELEGATED, REPLY_CAPTURED, REPLY_FIXTURE)

#: 解析状态；只有 `ok` 才允许进入静态扫描与装载。
PARSE_OK = "ok"
PARSE_EMPTY = "empty"
PARSE_MISSING_THOUGHT = "missing_thought"
PARSE_MISSING_CODE = "missing_code"
PARSE_AMBIGUOUS_CODE = "ambiguous_code"
#: 回复被截断（`finish_reason != "stop"`）：**不得当合法回复解析**。
#: 推理型模型尤其常见——正文为空、只有 `reasoning_content`（Lead 实测）。
PARSE_TRUNCATED = "truncated"

#: 允许 import 的模块（白名单，**不是**"只要不危险就放行"）。
#: 规则事实只能来自 `hangma`，评分接口只能来自已注册接缝；标准库只留纯计算所需。
ALLOWED_IMPORTS = frozenset({
    "__future__",
    "math",
    "dataclasses",
    "typing",
    "collections.abc",
    "hangma_bot.hangma.interface",
    "hangma_bot.hangma.progression",
    "hangma_bot.hangma.special_rules",
    "hangma_bot.kernel.actions",
    "hangma_bot.policy.heuristic_adapter",
    "hangma_bot.policy.evaluation_v1",
    "hangma_bot.policy.weights_v1",
})

#: 禁止的内建调用（候选必须是纯计算；本清单同样是 lint，不是边界）。
FORBIDDEN_CALLS = ("eval", "exec", "compile", "__import__", "open", "input",
                   "globals", "locals", "breakpoint")

#: 禁止的源码痕迹：本工具**自己的 lint 清单**（与门禁 G-1 的清单不共用实现、
#: 也没有一致性回归，故不声称"同源"）。它只用于**子进程外**的快速拒绝。
FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "import socket", "import urllib", "import httpx", "import requests",
    "import aiohttp", "import subprocess", "import shutil", "import tempfile",
    "import os", "import sys", "import random", "import time", "import pathlib",
    "import importlib", "import threading", "import multiprocessing",
    "open(", "os.", "Path(", ".write_text", ".read_text", ".read_bytes",
    "__import__(", "eval(", "exec(", "compile(",
)

#: 隔离装载的墙钟上限（秒）。口径是"拦住不会自己结束的运行"，不是性能门禁。
LOAD_TIMEOUT_SEC = 30.0
#: SIGTERM 之后的宽限；与门禁同一口径。
LOAD_TERM_GRACE_SEC = 5.0
#: 默认调用预算（次）。**先预留后调用**，失败与重试同样计费。
DEFAULT_CALLS_BUDGET = 8
#: 调用 token 的**累计上限**：超限即停止并记账（Lead 裁定 S5）。
DEFAULT_MAX_TOTAL_TOKENS = 400_000
#: 血缘修复深度上限（M1 链最长几步）——"失败修复受调用上限限制"。
DEFAULT_REPAIR_DEPTH = 2

#: 作用面动作类别（与 policy 侧 `action_kind()` 口径一致）。
ACTION_KINDS = ("chi", "peng", "gang", "discard", "pass", "hu")


def utc_now() -> str:
    """墙钟时间（UTC，ISO-8601 秒级）。与**单调耗时**分开记录，两者不可互相替代。"""

    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def short(digest: Optional[str], length: int = 12) -> str:
    return digest[:length] if digest else "-"


# ============================================================ 1. 任务合同


@dataclass(frozen=True)
class FactSpec:
    """一条**允许读物**：候选可以读取的既有事实。

    `expression`：读取表达式（例如 `candidate.facts.standard_shanten_after`）。
    `type_text`：类型文本。
    `unit`：单位与取值口径，**直接取自源码行内注释**（不手抄，避免与实现漂移）。
    `note`：来源或边界说明。
    """

    expression: str
    type_text: str
    unit: str
    note: str = ""


@dataclass(frozen=True)
class TaskContract:
    """I1/M1 提示词里的**任务合同**；它是提示词中事实部分的唯一来源。

    合同进提示词前先序列化并取哈希，因此"改了合同"必然改变提示词哈希，
    也就必然改变血缘记录——不允许出现"提示词变了但身份没变"。
    """

    task: str
    facts: Tuple[FactSpec, ...]
    function_contract: str
    units: Tuple[str, ...]
    limits: Tuple[str, ...]
    counterexamples: Tuple[str, ...]
    forbidden: Tuple[str, ...]

    def identity(self) -> str:
        """合同身份：对规范化 JSON 取哈希（用于对账提示词与合同版本）。"""

        return sha256_text(json.dumps(self.to_json(), ensure_ascii=False, sort_keys=True))

    def to_json(self) -> Dict[str, Any]:
        return {
            "schema": CONTRACT_SCHEMA,
            "task": self.task,
            "facts": [dataclasses.asdict(item) for item in self.facts],
            "function_contract": self.function_contract,
            "units": list(self.units),
            "limits": list(self.limits),
            "counterexamples": list(self.counterexamples),
            "forbidden": list(self.forbidden),
        }

    def render(self) -> str:
        """渲染成提示词里的「任务合同」段（中文，逐条可核对）。"""

        lines = ["【任务】", self.task, "", "【允许读取的事实（只有这些）】"]
        for item in self.facts:
            unit = "；单位/口径：" + item.unit if item.unit else ""
            note = "；说明：" + item.note if item.note else ""
            lines.append("  - {0}：{1}{2}{3}".format(item.expression, item.type_text, unit, note))
        lines += ["", "【函数合同（不得改动）】", self.function_contract, "",
                  "【单位与尺度约定】"]
        lines += ["  - " + text for text in self.units]
        lines += ["", "【硬限制（违反即拒绝装载）】"]
        lines += ["  - " + text for text in self.limits]
        lines += ["", "【必须写清反例（什么时候不该生效）】"]
        lines += ["  - " + text for text in self.counterexamples]
        lines += ["", "【禁止项】"]
        lines += ["  - " + text for text in self.forbidden]
        return "\n".join(lines)


#: 函数合同模板：**逐字**进提示词，也是静态扫描与装载阶段核验的入口签名。
CODE_TEMPLATE = '''from __future__ import annotations

from typing import Mapping

from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment
from hangma_bot.hangma.interface import RuleCandidate


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """按声明参数构造本候选。"""

    # <在这里实现你的机制；函数名与签名不得改动>
    raise NotImplementedError
'''


def gang_bonus_reference() -> float:
    """从 `weights_v1` 的**活动权重实例**读出 gang_bonus（提示词里的锚点值）。

    GL-8：初版把 40.0 抄死在提示词里，权重一改提示词就与实现漂移，
    而且没有任何回归会红。现在读真值；回归再把两侧绑起来。
    """

    from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

    return float(getattr(DEFAULT_WEIGHTS_V1, "gang_bonus"))


def gate_window_limit_ms() -> float:
    """从门禁源码里读出"单窗口硬上限"（GL-8：避免提示词与门禁常量漂移）。

    用**源码正则 + ast.literal_eval** 读，而不是 import 整个门禁工具：
    提示词构建不该为了一个常量把门禁的全部依赖拉起来。
    """

    path = _project_file(_PROJECT_ROOT, _HERE / "sitin_gates.py")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 50.0
    match = re.search(r"^G1_MAX_SINGLE_WINDOW_MS\s*=\s*([0-9.]+)", text, re.MULTILINE)
    if not match:
        return 50.0
    try:
        return float(ast.literal_eval(match.group(1)))
    except (ValueError, SyntaxError):
        return 50.0


def _inline_notes(cls: type) -> Dict[str, str]:
    """从**源码行内注释**提取字段说明，避免提示词里的单位说明与实现漂移。

    读不到源码（冻结环境、交互式定义）时返回空映射，并在合同里留空——
    **不编造单位说明**。
    """

    try:
        source = inspect.getsource(cls)
    except (OSError, TypeError):
        return {}
    notes: Dict[str, str] = {}
    for line in source.splitlines():
        stripped = line.strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", stripped)
        if not match or "#" not in line:
            continue
        notes.setdefault(match.group(1), line.split("#", 1)[1].strip())
    return notes


def _resolve_class(dotted: str) -> type:
    module_name, _, class_name = dotted.rpartition(":")
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


#: 允许面的**唯一来源**：真实运行时的公开类型。`check_surface()` 会核对它们仍然存在。
SURFACE_SOURCES: Tuple[Tuple[str, str, str], ...] = (
    ("candidate.facts", "hangma_bot.hangma.interface:CandidateFacts", "动作后牌效事实"),
    ("ctx", "hangma_bot.policy.evaluation_v1:EvaluationContext", "窗口内不变的评分上下文"),
)

#: 函数契约里附带的"只读入参"说明（它们不是 dataclass 字段，因此单列）。
SURFACE_EXTRA: Tuple[FactSpec, ...] = (
    FactSpec("candidate.action_key", "str",
             "动作键，形如 `peng:1w`；动作种类由 `:` 前一段给出",
             "只读；**不得**据它判断合法性"),
    FactSpec("candidates", "Tuple[RuleCandidate, ...]",
             "本窗口规则给出的全部候选（只读）",
             "需要跨候选的量时才读；**不得**改变候选集合"),
)


def check_surface() -> Dict[str, Any]:
    """核验合同声明的允许面**仍在当前源码里存在**；缺字段即失败。

    这是防止"提示词里的 API 与真实接驳面漂移"的最小手段：候选是按提示词写的，
    提示词若写了不存在的字段，生成端会系统性地产出不可装载的代码。
    """

    problems: List[str] = []
    seen: Dict[str, Any] = {}
    for label, dotted, _note in SURFACE_SOURCES:
        try:
            cls = _resolve_class(dotted)
        except Exception as exc:                      # noqa: BLE001 —— 解析失败同样是失败
            problems.append("允许面来源不可解析：{0}（{1}）".format(dotted, exc))
            continue
        if not dataclasses.is_dataclass(cls):
            problems.append("允许面来源不是 dataclass：{0}".format(dotted))
            continue
        seen[label] = sorted(field.name for field in dataclasses.fields(cls))
    return {"ok": not problems, "problems": problems, "fields": seen}


def build_facts() -> Tuple[FactSpec, ...]:
    """按 `SURFACE_SOURCES` 生成允许读物清单（单位取自源码行内注释）。"""

    facts: List[FactSpec] = []
    for label, dotted, note in SURFACE_SOURCES:
        cls = _resolve_class(dotted)
        notes = _inline_notes(cls)
        for field in dataclasses.fields(cls):
            expression = "{0}.{1}".format(label, field.name)
            type_text = getattr(field.type, "__name__", None) or str(field.type)
            facts.append(FactSpec(expression, type_text, notes.get(field.name, ""), note))
    facts.extend(SURFACE_EXTRA)
    return tuple(facts)


def default_task_contract() -> TaskContract:
    """默认任务合同：一条**可装载**的价值路径候选的最小任务描述。

    任务刻意写得窄：本轮目标是"闭环能跑、拒绝路径有效"，不是"生成好候选"。
    """

    return TaskContract(
        task=(
            "为杭麻 Bot 的启发式评分写一个**有界评分调整**候选：它按官方番型倍率路径"
            "（分支 / 动作链 / 四白 / 爆头）组织，只读上面列出的既有事实，"
            "在候选总分上追加一个分项。**不要**重算规则、**不要**判断合法性、"
            "**不要**改变候选集合或排序。"
        ),
        facts=build_facts(),
        function_contract=(
            "入口固定为 `build_adjustment_from_params(params: Mapping[str, float], "
            "source_fingerprint_value: str = \"\") -> HeuristicAdjustment`，"
            "参数个数与默认值都不得改动；返回的 `AdjustmentSpec` 必须给出"
            "非空的 name/version/thought/trigger、非空的 scope（取值取自 "
            "chi/peng/gang/discard/pass/hu）与正的 bound。\n"
            "适配器固定的 delta 签名是 `delta(candidate: RuleCandidate, "
            "ctx: EvaluationContext, candidates: Tuple[RuleCandidate, ...]) -> float`。"
        ),
        units=(
            # 数值**从源码读**（GL-8）：措辞保持与历史一致，只有真值变了提示词才变。
            "delta 的单位是**评分点**（与 V1 既有分项同一尺度，例如 gang_bonus={0}）；"
            "不得据此下「这就是分数或番数」的结论。".format(gang_bonus_reference()),
            "若写成势差 Φ(s′)−Φ(s)，必须在说明里写出同一个 Φ 与适用域；"
            "门控要进 Φ（Φ=Σ g_i(s)·φ_i(s) 再取差），不得只对动作后开关。",
            "倍率与评分点的换算必须显式写成一个参数（例如 scale = 评分点 / log2 番），"
            "不得把 ×2 直接当 +2 分。",
        ),
        limits=(
            "delta 必须是**有限**浮点数；无适用条件时返回 0.0（**不加不减**），"
            "不得返回 None、NaN 或 inf。",
            "|delta| ≤ 你在 `AdjustmentSpec.bound` 里声明的上限；**不得**在候选内部先裁剪，"
            "再靠适配器的钳制计数为零掩盖越界。",
            "纯函数：同输入同输出；不得有文件、网络、时间、随机、全局可变状态或跨调用缓存。",
            "不得做搜索、不得重算向听或有效牌、不得读取未来牌墙或其他玩家手牌。",
            "import 只能用白名单：" + "、".join(sorted(ALLOWED_IMPORTS)) + "。",
            "事实缺失或不完整（`facts is None` 或 "
            "`completeness is not COMPLETE`）必须以 0.0 退回，"
            "不许用 0 冒充「已知为 0」。",
            # 同上：数值从门禁源码读出，措辞不变。
            "每个被触发窗口的额外耗时必须在毫秒级（门禁 G-1 的单窗口硬上限为 {0:g} ms）。".format(
                gate_window_limit_ms()),
        ),
        counterexamples=(
            "已胡候选（`facts.fact_kind is WIN`）：路径已经兑现，"
            "不得当成「被打掉」而扣分。",
            "纯弃牌窗口没有参考状态（没有过牌候选可代表动作前状态）时，势差**不适用**，"
            "必须返回 0.0 并写进 trigger 说明。",
            "杠后补牌未知（`replacement_draw_unknown=True`）时不得假设具体未来摸牌。",
            "链内飘出数未知（`ctx.chain_piao is None`）时不得当 0；四白是**等值条件**"
            "（手留白 + 链内飘出恰好等于 4），不是单调量。",
        ),
        forbidden=(
            "禁止读取 `WorldState`、官方 DTO、Token、磁盘、系统时间与随机源。",
            "禁止提交动作、禁止声明某个动作合法、禁止重排候选或改变 rank。",
            "禁止 `open`/`eval`/`exec`/`compile`/"
            "`__import__` 与白名单之外的 import。",
            "禁止在候选内部静默裁剪到 bound 以内。",
            "禁止把「势差可保持最优策略」写成已证明的事实（那是累计奖励变换的结论，"
            "单步启发式没有该保证）。",
        ),
    )


# ============================================================ 1b. action_value_v1 生成路径
#
# §10 R-E 提示词合同：TaskContract 由机器合同 contracts/action-value-v1.json
# 渲染（白名单/限额/禁令/输出合同**全部从 JSON 读**，不手写第二套——同源
# 测试在 test_sitin_search_v4.py：改 JSON 一个限额值 → 渲染文本变化，且与
# 执行器实际校验值对账一致）。旧 delta 生成路径原义不动：
# --candidate-kind action_value_v1 走本节，缺省走旧路径。
# ============================================================

#: 新候选种类与入口名（与合同 candidate_kind / entry_point.signature 一致）。
AV_CANDIDATE_KIND = "action_value_v1"
AV_ENTRY_NAME = "score_actions"
#: 新路径血缘记录 schema（独立于旧 sitin-generation-record/1，不混写）。
AV_GENERATION_SCHEMA = "sitin-action-value-generation/1"
#: 新路径任务合同 schema。
AV_TASK_CONTRACT_SCHEMA = "sitin-action-value-task-contract/1"
#: 机器合同相对仓库根路径（唯一来源；与 sitin_gates.av_contract 同一文件）。
AV_CONTRACT_RELPATH = Path("review/llm-guided-heuristic-route-2026-09-15"
                           "/contracts/action-value-v1.json")
#: 受限子集规则目录（AV-SUB ×60）的**兄弟文件**。为什么不放进合同：合同字节 sha 是
#: 冻结评价身份的一部分（gate-2 计划文件、全部评价/面板身份记录、金例身份键
#: av_contract_sha256 都引用它），而规则目录只描述"候选可见的约束"，不改任何评分语义——
#: 放进合同会让已签收的关口二链身份无谓失效。本文件**不进合同身份**。
AV_SUBSET_RULES_RELPATH = Path("review/llm-guided-heuristic-route-2026-09-15"
                               "/contracts/action-value-restricted-rules-v1.json")
#: 公开接口附录（C5）与规则目录同为**兄弟文件**：合同字节 sha 是冻结评价身份的一部分，
#: 附录只把「候选实际读到的字段名/路径/形状/类型/单位/枚举/可空条件」写清楚，不改任何
#: 评分语义，因此同样不进合同字节身份；它的 sha 进**提示词 payload 身份**。
AV_PUBLIC_INTERFACE_RELPATH = Path("review/llm-guided-heuristic-route-2026-09-15"
                                   "/contracts/action-value-public-interface-v1.json")
#: 目标合同（group-dev-v1）：终端 U 的定义来源，用于缺省目标摘要。
AV_GROUP_CONTRACT_RELPATH = Path("review/llm-guided-heuristic-route-2026-09-15"
                                 "/contracts/group-dev-v1.json")
#: §10 结构化四字段（触发条件/改变的动作分支/预期方向/反例）。
AV_MECHANISM_FIELDS = (
    "trigger", "changed_branches", "expected_direction", "counterexample",
)
#: 四字段各自的写法要求（**单一来源**：生成题与 kind=code 的修复题都从这里渲染，
#: 不存在两套措辞）。判分器 require_mechanism 只查"四键齐且非空"，这里是给作者的说明。
AV_MECHANISM_FIELD_NOTES = {
    "trigger": "触发条件：什么局面下本机制改变排序",
    "changed_branches": "改变的动作/分支：哪些动作或分支相对移动；"
                        "M1 修订必须写出至少一处与父代的差异"
                        "（窗口类 + 动作键 + 分值变化或次序反转），写不出即视为无实质变更",
    "expected_direction": "预期方向：预期哪类面板上变好/变差（不要求自报提分数值）",
    "counterexample": "反例：什么局面下本机制不该生效或会变差",
}
#: 受限子集静态规则的适用题类闭集（规则目录 rules[].applies_to）。
#: 执行器对生成题与修复题跑的是**同一份** static_check，因此 60 条规则两类同
#: 适用；本字段的用途是让渲染器按题类过滤，缺表的那一类必须显式可见（不静默）。
AV_SUBSET_RULE_TARGETS: Tuple[str, ...] = ("generation", "repair")
#: 修复题提示词的 operator 标识（生成题用 OPERATOR_I1 / OPERATOR_M1）。
AV_OPERATOR_REPAIR = "repair"
#: 解析状态：四字段缺失（代码可有，但机制说明不完整不得装载）。
PARSE_MISSING_MECHANISM = "missing_mechanism"

_AV_CONTRACT_CACHE = {}


def load_action_value_contract(path=None):
    """读机器合同 action-value-v1.json；返回 (合同, sha256)。

    这是新路径 TaskContract 渲染的**唯一来源**：改 JSON 的一个限额值，
    渲染文本随之变化（同源测试据此对账），不维护第二套允许范围。
    """

    target = Path(path) if path is not None else (_project_file(_PROJECT_ROOT, REPO / AV_CONTRACT_RELPATH))
    key = str(target)
    if key not in _AV_CONTRACT_CACHE:
        raw = target.read_bytes()
        _AV_CONTRACT_CACHE[key] = (json.loads(raw.decode("utf-8")),
                                   hashlib.sha256(raw).hexdigest())
    return _AV_CONTRACT_CACHE[key]


_AV_SUBSET_RULES_CACHE: Dict[str, Any] = {}


def load_action_value_subset_rules(path=None):
    """读受限子集规则目录（兄弟文件）；返回 (规范化规则清单, 文件 sha256)。

    与 load_action_value_contract 同一纪律：**唯一来源**、按路径缓存、渲染与预检共用；
    唯一区别是本文件不进合同身份（见 AV_SUBSET_RULES_RELPATH 注释）。
    """

    target = Path(path) if path is not None else (_project_file(_PROJECT_ROOT, REPO / AV_SUBSET_RULES_RELPATH))
    key = str(target)
    if key not in _AV_SUBSET_RULES_CACHE:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        _AV_SUBSET_RULES_CACHE[key] = (normalize_subset_rules(payload.get("rules")),
                                       hashlib.sha256(raw).hexdigest())
    return _AV_SUBSET_RULES_CACHE[key]


def default_objective_summary() -> str:
    """缺省目标摘要：终端 U 定义从目标合同 group-dev-v1.json 读（同源纪律）。"""

    try:
        data = json.loads((_project_file(_PROJECT_ROOT, REPO / AV_GROUP_CONTRACT_RELPATH)).read_text(
            encoding="utf-8"))
        objective = data.get("objective") or {}
        return str(objective.get("utility") or data.get("target", {}).get(
            "goal") or "group_advance_v1（读目标合同失败，U 定义以合同文件为准）")
    except (OSError, ValueError):
        return "group_advance_v1（目标合同不可读；U 定义以合同文件为准）"


# ============================================================ 1c. 门线/位次势差口径（M4）
#
# 复审 §5 M4：候选文档写「晋级门线（第 3 名分数线）」，公式却是升序
# `sorted(scores)[2]`——升序下标 2 是**第 2 名**，名实不符。本节是该口径的
# **唯一来源**：作者提示词从这里渲染（同源），金例测试
# （tools/test_sitin_generate_gate_line.py）对同一批函数逐值手算核对。
#
# 参考实现刻意写在受限子集内（无 import/while/递归/try/注解/默认参数），
# 作者可**逐字复制**成候选内的局部纯辅助函数；它不是运行时评分路径，
# 也不改变候选的职责边界（候选仍只读同一份只读可见事实）。

#: 晋级区座位数：从冻结目标合同 objective.advance_count 读；读不到用缺省值（不编造）。
GATE_ADVANCE_FALLBACK = 2
#: 动作后门线势差的两种模式名：必须在机制说明里显式声明其一。
GATE_LINE_MODE_RECOMPUTE = "recompute"    # 完整结算向量重算（四座积分都有值才允许）
GATE_LINE_MODE_FROZEN = "frozen_line"      # 只加本人增量、门线固定（近似启发式）
#: 禁止的命名（名实必须一致）：每一条都对应复审 §5 M4 的一种误用。
GATE_LINE_FORBIDDEN_NAMINGS = (
    "不得把升序下标 2（第 2 名分数）叫「第 3 名门线」或「第三名分数线」",
    "不得把升序下标 1（第 3 名分数）叫「第 2 名门线」",
    "不得用未注明第几名的「门线」同时指代晋级区末位与区外头名",
)
#: 升序下标 → 名次（第 k 名 = 升序下标 4−k）；提示词里逐条列出。
GATE_ORDER_PLACES = ((0, "第 4 名"), (1, "第 3 名"), (2, "第 2 名"), (3, "第 1 名"))
#: 禁止的**陈述**（不只是命名）：每一条都是数学上不成立、却容易被作者照抄进机制说明的
#: 说法。R8 E3/M2 复审原文：① frozen_line 的 δ 逐动作取值，不是公共平移；
#: ② recompute 下 Φ 连续且分段线性，ΔΦ 可以等于本人增量。引用即禁止。
GATE_LINE_FORBIDDEN_CLAIMS = (
    "不得写「δ 是公共平移、不改变本窗口排序」：δ 逐动作取值，同一窗口内不同动作的"
    "结算增量可以分别为 +5 与 +15，势差也分别为 +5 与 +15；只有全部动作共享同一个"
    "常数平移时排序才不变",
    "不得写「recompute 下 ΔΦ ≠ 本人增量」这种绝对式：门线数值在本动作后未变时 "
    "ΔΦ 恰等于本人增量（例如本人增量 +60、门线仍为 80）",
    "不得写「跨越名次门线时势值不连续」：积分门线势 Φ 是连续的分段线性函数，"
    "跨线改变的是斜率；不连续只属于离散名次与晋级指示",
)

#: competition_bases 里**已具名渲染**的键；其余键由渲染器自动追加（P11 缺陷类：
#: 合同新增字段却进不了提示词，候选因此读不到阶段账）。旧键改名即退化为自动渲染，
#: 不会静默丢失。
AV_COMPETITION_NAMED_KEYS = (
    "seat_order", "units", "stage_scores", "table_scores", "current_stage_scores",
    "identity_mapping", "admission_conditions", "unknown_is_not_zero",
    "freshness_masks", "staleness", "residual_risk", "residual_gaps",
)


def gate_advance_count():
    """读目标合同 objective.advance_count（晋级区座位数）；返回 (值, 是否读到合同)。"""

    try:
        data = json.loads((_project_file(_PROJECT_ROOT, REPO / AV_GROUP_CONTRACT_RELPATH)).read_text(encoding="utf-8"))
        value = (data.get("objective") or {}).get("advance_count")
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 3:
            return value, True
    except (OSError, ValueError):
        pass
    return GATE_ADVANCE_FALLBACK, False


def gate_line_indices(advance_count):
    """升序下标 ↔ 名次唯一映射：第 k 名分数 = 升序下标 (4−k)。"""

    if isinstance(advance_count, bool) or not isinstance(advance_count, int):
        raise ValueError("advance_count 必须是整数")
    if advance_count < 1 or advance_count > 3:
        raise ValueError("advance_count 必须在 1—3（四人桌且至少一个区外座位）")
    return {"inside_line_index": 4 - advance_count,
            "outside_line_index": 4 - advance_count - 1}


# —— 参考实现（受限子集内；本节是公式的唯一来源，金例测试逐值核对）——


def gate_line_values(scores):
    """门线参考实现：同一基准的四座积分 → 各名次分数；任一未知返回 None。

    返回 {"first"/"second"/"third"/"fourth": 名次分数}；None 表示未知
    （不得用 0 冒充）。名次与升序下标的对应是唯一映射：第 k 名 = 下标 4−k。
    非有限数（NaN/inf）同样未知：value − value ≠ 0 即拒绝（子集内没有 math）。
    """

    if scores is None or len(scores) != 4:
        return None
    values = []
    for item in scores:
        if item is None or item is True or item is False:
            return None
        value = float(item)
        if value - value != 0:
            return None
        values.append(value)
    ordered = sorted(values)
    return {"first": ordered[3], "second": ordered[2],
            "third": ordered[1], "fourth": ordered[0]}


def gate_line_potentials(scores, seat):
    """两条门线势差（积分）：inside_gap 追第 2 名、outside_gap 领先第 3 名。

    inside_gap  = s[seat] − inside_line  = s[seat] − 第 2 名分数（晋级区末位）
    outside_gap = s[seat] − outside_line = s[seat] − 第 3 名分数（区外头名）
    任一座缺失/布尔/非有限、座位越界 → None（未知不伪装成 0）。
    """

    if seat is None or seat is True or seat is False:
        return None
    if seat < 0 or seat > 3:
        return None
    lines = gate_line_values(scores)
    if lines is None:
        return None
    own = scores[seat]
    if own is None or own is True or own is False:
        return None
    own_value = float(own)
    if own_value - own_value != 0:
        return None
    return {"inside_line": lines["second"], "outside_line": lines["third"],
            "inside_gap": own_value - lines["second"],
            "outside_gap": own_value - lines["third"]}


def gate_line_delta_recomputed(scores, seat, deltas):
    """完整结算向量重算：deltas 是动作后**四座**积分增量；任一座未知即 None。

    Δinside_gap = Φ_in(s′) − Φ_in(s)、Δoutside_gap = Φ_out(s′) − Φ_out(s)，
    其中 s′ = s + deltas（四个座位都有值才算重算）。门线自身会移动，
    因此 ΔΦ 一般**不等于**本人增量——但可以相等：门线数值在本动作后未变时
    ΔΦ 恰等于本人增量（例如本人增量 +60、门线仍为 80 时 ΔΦ = +60）。
    门线是顺序统计量，Φ(s) = s[seat] − 第 k 名分数 连续且分段线性；
    跨过名次门线时改变的是斜率，不是势值不连续。
    """

    before = gate_line_potentials(scores, seat)
    if before is None:
        return None
    if deltas is None or len(deltas) != 4:
        return None
    after_scores = []
    for index in range(0, 4):
        item = scores[index]
        step = deltas[index]
        if item is None or item is True or item is False:
            return None
        if step is None or step is True or step is False:
            return None
        moved = float(item) + float(step)
        if moved - moved != 0:
            return None
        after_scores.append(moved)
    after = gate_line_potentials(after_scores, seat)
    if after is None:
        return None
    return {"mode": "recompute",
            "delta_inside": after["inside_gap"] - before["inside_gap"],
            "delta_outside": after["outside_gap"] - before["outside_gap"],
            "inside_line_moved": after["inside_line"] != before["inside_line"],
            "outside_line_moved": after["outside_line"] != before["outside_line"]}


def gate_line_delta_frozen_line(scores, seat, own_delta):
    """近似启发式：只把本人增量加到本座位、门线数值固定在动作前取值。

    此时 Δinside_gap = Δoutside_gap = 本人增量（恒等式），门线**不**移动；
    只能称「近似启发式」，适用域仅限同一窗口内比较本座位各合法动作。
    δ 是**逐动作**取值，不是公共平移：同一窗口内不同动作的 δ 可以不同
    （例如 +5 与 +15），势差与排序都可以随之改变；只有全部动作共享同一个
    常数平移时排序才不变。
    """

    before = gate_line_potentials(scores, seat)
    if before is None:
        return None
    if own_delta is None or own_delta is True or own_delta is False:
        return None
    value = float(own_delta)
    if value - value != 0:
        return None
    return {"mode": "frozen_line",
            "delta_inside": value, "delta_outside": value,
            "inside_line_moved": False, "outside_line_moved": False}


def gate_zone_status(keys, seat, advance_count):
    """名次识别区间与晋级三态；同分/缺次级键时给区间，不塌缩成确定名次。

    keys 是四座**可比键**：缺次级排序事实时用总积分（同分进同一并列块），
    次级键（place_points/god_count）齐备时用 (总积分, 名次分, …) 元组。
    low  = 严格更高者数 + 1；high = 严格更高者数 + 同块人数；
    high ≤ 晋级区 → IN；low > 晋级区 → OUT；其余 UNRESOLVED。
    """

    if keys is None or len(keys) != 4:
        return None
    if seat is None or seat is True or seat is False:
        return None
    if seat < 0 or seat > 3:
        return None
    if advance_count is None or advance_count is True or advance_count is False:
        return None
    if advance_count < 1 or advance_count > 3:
        return None
    higher = 0
    equal = 0
    for index in range(0, 4):
        item = keys[index]
        if item is None:
            return None
        if item == keys[seat]:
            equal += 1
        elif item > keys[seat]:
            higher += 1
    low = higher + 1
    high = higher + equal
    zone = "UNRESOLVED"
    if high <= advance_count:
        zone = "IN"
    elif low > advance_count:
        zone = "OUT"
    return {"low": low, "high": high, "zone": zone}


# —— 提示词里的手算金例（值由上面的参考实现算出，不手抄）——

#: 静态金例：(标签, 四座积分按座位 0—3, 焦点座位)。
GATE_LINE_GOLDEN_CASES = (
    ("领先（第 1 名）", (100.0, 80.0, 20.0, 0.0), 0),
    ("临界（并列第 2）", (100.0, 80.0, 80.0, 0.0), 1),
    ("落后（复审 §5 M4 实例）", (100.0, 80.0, 20.0, 0.0), 2),
    ("末位", (100.0, 80.0, 20.0, 0.0), 3),
    ("同分（三人在争两个席位）", (50.0, 50.0, 50.0, 0.0), 0),
)
#: 完整结算向量重算金例：(标签, 四座积分, 焦点座位, 四座增量)。
GATE_LINE_GOLDEN_RECOMPUTES = (
    ("完整结算向量重算（本人越过门线）", (100.0, 80.0, 20.0, 0.0), 2,
     (0.0, 0.0, 70.0, 0.0)),
    ("完整结算向量重算（只他家结算、本人增量为 0）", (100.0, 80.0, 20.0, 0.0), 2,
     (0.0, -30.0, 0.0, 0.0)),
)
#: 近似启发式金例：(标签, 四座积分, 焦点座位, 本人增量)。
GATE_LINE_GOLDEN_FROZEN = (
    ("近似启发式（只加本人增量、门线固定）", (100.0, 80.0, 20.0, 0.0), 2, 70.0),
)


def _gate_exact(value):
    """金例数字的**精确保真**文本：整值不带小数点，其余按 repr 原样（不丢有效位）。

    "{0:g}" 只有 6 位有效数字，会把 60.000001 吞成 60 —— 连续拐点金例正是靠
    60.000001 与 60 的差别证明「ΔΦ 连续但可以等于本人增量」，因此那些行必须用本函数。
    """

    number = float(value)
    if number == int(number):
        return str(int(number))
    return repr(number)


def _gate_exact_signed(value):
    number = float(value)
    return ("+" if number >= 0 else "") + _gate_exact(number)


def _gate_number(value):
    """金例数字的稳定文本（整数不带小数点，便于提示词与测试逐字对账）。"""

    return "{0:g}".format(value)


def _gate_signed(value):
    return "{0:+g}".format(value)


def _gate_vector_text(values):
    return ", ".join(_gate_number(item) for item in values)


def gate_line_clauses():
    """门线口径条款（唯一允许的定义/公式/命名/适用域）；值取自冻结合同。"""

    advance, _ = gate_advance_count()
    indices = gate_line_indices(advance)
    return (
        "事实基线：晋级区 = 阶段排名前 {0}（目标合同 objective.advance_count={0}）；"
        "名次键链 total_score → place_points → god_count → user_id。".format(advance),
        "唯一映射：升序下标 0=第 4 名、1=第 3 名、2=第 2 名、3=第 1 名"
        "（第 k 名分数 = 升序下标 4−k）。写「门线」前先写下标对应第几名。",
        "账的三个概念（先分辨再算，不得混称）：已完成账 = competition.stage_scores"
        "（本阶段【已完成各桌】的积分和，按物理座位 0—3；不含当前桌进行中积分、"
        "不含名次分、不含未来桌赛结果）；当前桌账 = competition.table_scores"
        "（本桌【进行中】积分，同座位序、同单位；与 visible_state.table_scores / "
        "visible_state.scores 是同一事实的两个基准名）；当前阶段合计 = "
        "competition.current_stage_scores = 已完成账 + 当前桌账，逐座位相加 "
        "current_stage_scores[i] = stage_scores[i] + table_scores[i]。"
        "两项互不重叠（一项只含已完成桌、一项只含本桌进行中），因此相加是"
        "**重建完整当前阶段分数**，不是重复累计。算当前阶段名次与门线必须用"
        "当前阶段合计（current_stage_scores，或经核验同座位、同单位、互不重叠的 "
        "stage_scores + table_scores 两账相加并显式命名来源）：只加已完成账会把"
        "当前领先者当落后者（已完成账里落后、加上本桌进行中积分后领先），"
        "只看本桌积分也不是阶段门线（本桌之外还有已完成桌的账）。"
        "唯一禁止的重复累计：table_scores 与同一份 visible_state.table_scores 相加"
        "——两者是同一事实的两个基准名，相加等于把本桌积分算两次。",
        "缺账口径：stage_scores 缺账（freshness_masks 给出 stage_account:absent 或 "
        "stage_account:unmappable）时，stage_scores 与 current_stage_scores 同时为"
        "**未知**（null）：不得当 0、不得当「四家同分」、不得用 table_scores 或 "
        "visible_state.scores 顶替当阶段账——这与作者守卫条款的「未知 ≠ 0」是"
        "同一条不变量，不是第二套说法；反之驱动注入的四座全 0 账是**已知的零**"
        "（stage_account:complete），照常可用。",
        "可见赛程**未投影**（合同 competition_bases.residual_gaps 已登记为剩余缺口）："
        "候选视图只有积分与掩码，不含剩余桌数、阶段总桌数或任何可反推它们的字段"
        "（把剩余桌数从 0 改为 6，候选视图逐字不变）。因此不得把「最后机会追分」"
        "「仍有多桌可保守」当成可见事实来声称；要写这类判断，必须先声明剩余赛程"
        "不可见，并说明不依赖它时的决策口径。",
        "命名与公式（只有这两个，名字必须与所用下标一致）："
        "inside_line（晋级区末位门线，别名「追第二名」）= 升序下标 {0} 的分数 = 第 {1} 名分数，"
        "Φ_in = s[seat] − inside_line（Φ_in ≥ 0 表示积分不低于第 {1} 名，并列计入）；"
        "outside_line（区外头名门线，别名「领先第三名」）= 升序下标 {2} 的分数 = 第 {3} 名分数，"
        "Φ_out = s[seat] − outside_line（Φ_out > 0 表示严格领先区外头名）。".format(
            indices["inside_line_index"], advance,
            indices["outside_line_index"], advance + 1),
        "动作后门线势差只有两种模式，必须在机制说明里显式声明其一（不得默认、不得混称）："
        "recompute（完整结算向量重算）要求动作后**四座积分全部已知**"
        "（immediate_settlement.score_delta 就是四座齐全的增量向量），"
        "ΔΦ = Φ(s′) − Φ(s)；任一座未知即未知，不得称重算、不得当 0、不得当门线不变。"
        "frozen_line（近似启发式）只把本人增量 δ 加到本座位、门线数值固定为动作前取值，"
        "此时 ΔΦ = δ 对本座位**每一个**合法动作逐动作恒成立（δ 因动作而异：同一窗口内"
        "不同动作的结算增量可以分别为 +5 与 +15，势差也分别为 +5 与 +15），所以"
        "**不得**写「δ 是公共平移、不改变本窗口排序」——只有同一窗口内**全部动作共享"
        "同一个常数平移**时排序才不变。",
        "两种模式的差别（必写进机制说明）：recompute 下门线自身随四座向量移动，"
        "因此 ΔΦ **一般不等于**本人增量；但这是「有时成立」而不是恒真——门线数值在"
        "本动作后没变时 ΔΦ 就恰等于本人增量（金例本人增量 +60 的一行）。"
        "Φ(s) = s[座位] − 门线分数 是**连续**的分段线性函数：跨过名次门线时改变的"
        "是**斜率**（拐点），不是势值不连续——「跨越处不连续」只属于离散名次与"
        "晋级指示，不属于积分门线势。ΔΦ = 本人增量在 frozen_line 下**总是成立**，"
        "在 recompute 下只是**有时成立**。只加本人增量、固定他家门线的写法只能称"
        "「近似启发式」，不得据此声称门线会移动、名次会变或晋级概率已计入。",
        "同分与缺次级键：同分不改变门线数值，却改变「谁是第 k 名」；Φ=0 时是否在晋级区内"
        "按识别区间给（low = 严格更高者数+1，high = 严格更高者数+同块人数；"
        "high ≤ 晋级区 → IN；low > 晋级区 → OUT；其余 UNRESOLVED），"
        "次级键（place_points/god_count）未知时保留区间，"
        "不得用座位序或任意键序把区间塌缩成一个确定名次。",
        "未知不伪装零：基准缺失或陈旧、长度不是 4、含 None/布尔/非有限数 → 势差为未知"
        "（ABSTAIN 或写明缺项）；0 只能表示「已算出的相等」，不能表示「不知道」。",
        "平移不变：四座同加任意常数 c 时两条势差都不变（Φ(s + c·1⁴) = Φ(s)）；"
        "绝对积分水平不是门线势差。同一份本桌积分的两个基准名"
        "（competition.table_scores 与 visible_state.table_scores）不得相加；"
        "已完成账与当前桌账互不重叠，合成为当前阶段合计是允许且必需的"
        "（见「账的三个概念」）。",
        "单调性适用域：门线数值固定时 Φ 关于本座位积分单调不减；「向听更低更好」只对"
        "同一动作族、同一合法性集合、其余事实相同的比较成立（大牌路线可能牺牲向听换番），"
        "不得写成任何局面都成立。",
    )


#: M1 零合金例（复审 §5）：(已完成账, 当前桌账, 焦点座位)。三份向量的金线势差全部
#: 由参考实现 gate_line_potentials 算出，合计由两账逐座位相加得出——提示词不手抄数字。
STAGE_COMPOSITION_GOLDEN = (
    ((60.0, 40.0, -20.0, -80.0), (-100.0, 0.0, 100.0, 0.0), 2),
)

#: M2 连续拐点金例（复审 §5）：同一局面（四座 (100, 80, 20, 0)、焦点座位 2）只改本人
#: 增量，跨过第 2 名分数线 80——Δinside_gap 依次为 59.999999 / 60 / 60，体现连续拐点，
#: 且 60 那一行 ΔΦ 恰等于本人增量（recompute 下「不等于」不是恒真）。
GATE_LINE_CONTINUITY_SCORES = (100.0, 80.0, 20.0, 0.0)
GATE_LINE_CONTINUITY_SEAT = 2
GATE_LINE_CONTINUITY_GOLDEN = (59.999999, 60.0, 60.000001)


def stage_composition_golden_rows():
    """阶段账金例（三概念）：已完成账 / 当前桌账 / 当前阶段合计 + 结论行。"""

    advance, _ = gate_advance_count()
    rows = []
    for completed, table, seat in STAGE_COMPOSITION_GOLDEN:
        composite = tuple(
            completed[index] + table[index] for index in range(0, 4))
        for label, vector in (("已完成账", completed), ("当前桌账", table),
                              ("当前阶段合计", composite)):
            gaps = gate_line_potentials(vector, seat)
            status = gate_zone_status(vector, seat, advance)
            rows.append("  - 阶段账金例·{0}：四座积分（座位 0—3）=({1})；焦点座位={2}；"
                        "inside_line={3}；inside_gap={4}；名次区间=[{5},{6}]（{7}）".format(
                            label, _gate_vector_text(vector), seat,
                            _gate_number(gaps["inside_line"]),
                            _gate_number(gaps["inside_gap"]),
                            status["low"], status["high"], status["zone"]))
        completed_gaps = gate_line_potentials(completed, seat)
        composite_gaps = gate_line_potentials(composite, seat)
        rows.append(
            "  - 阶段账金例结论：只看已完成账得 inside_gap={0}（名次区间 {1}），"
            "只看当前桌账得 inside_gap={2}，合成的当前阶段合计得 **{3}**"
            "（名次区间 {4}）；只加已完成账会把当前领先者当落后者，"
            "只看本桌积分也不是阶段门线。".format(
                _gate_signed(completed_gaps["inside_gap"]),
                gate_zone_status(completed, seat, advance)["zone"],
                _gate_signed(gate_line_potentials(table, seat)["inside_gap"]),
                _gate_signed(composite_gaps["inside_gap"]),
                gate_zone_status(composite, seat, advance)["zone"]))
    return tuple(rows)


def gate_line_continuity_rows():
    """连续拐点金例行（值全部由 gate_line_delta_recomputed 算出，不手抄）。"""

    rows = []
    measured = []
    for own_delta in GATE_LINE_CONTINUITY_GOLDEN:
        before = gate_line_potentials(GATE_LINE_CONTINUITY_SCORES,
                                      GATE_LINE_CONTINUITY_SEAT)
        after_vector = []
        for index in range(0, 4):
            step = own_delta if index == GATE_LINE_CONTINUITY_SEAT else 0.0
            after_vector.append(GATE_LINE_CONTINUITY_SCORES[index] + step)
        after = gate_line_values(after_vector)
        moved = gate_line_delta_recomputed(
            GATE_LINE_CONTINUITY_SCORES, GATE_LINE_CONTINUITY_SEAT,
            tuple(own_delta if index == GATE_LINE_CONTINUITY_SEAT else 0.0
                  for index in range(0, 4)))
        measured.append(moved["delta_inside"])
        rows.append("  - 连续拐点金例（本人增量 {0}）：四座积分（座位 0—3）=({1})；"
                    "焦点座位={2}；本人增量 {3}；inside_line {4}→{5}（移动={6}）；"
                    "Δinside_gap={7}".format(
                        _gate_exact(own_delta),
                        _gate_vector_text(GATE_LINE_CONTINUITY_SCORES),
                        GATE_LINE_CONTINUITY_SEAT,
                        _gate_exact_signed(own_delta),
                        _gate_exact(before["inside_line"]),
                        _gate_exact(after["second"]),
                        moved["inside_line_moved"],
                        _gate_exact_signed(moved["delta_inside"])))
    rows.append(
        "  - 连续拐点序列（同一局面只改本人增量）：本人增量 {0} → Δinside_gap {1}"
        "（连续、无跳变；跨过第 2 名分数线时改变的是斜率，不是势值不连续）；"
        "其中 {2} 一行 Δinside_gap 恰等于本人增量，故 recompute 下"
        "「ΔΦ ≠ 本人增量」不是恒真。".format(
            "/".join(_gate_exact_signed(item) for item in GATE_LINE_CONTINUITY_GOLDEN),
            "/".join(_gate_exact_signed(item) for item in measured),
            _gate_exact_signed(GATE_LINE_CONTINUITY_GOLDEN[1])))
    return tuple(rows)


def gate_line_golden_rows():
    """金例行文本（静态 + 两种模式 + 阶段账三概念 + 连续拐点）。

    值全部由参考实现算出，避免提示词与算式漂移；E3 的 M1/M2 金例追加在**末尾**，
    不改变既有行的先后（既有用例按第一处命中取行）。
    """

    advance, _ = gate_advance_count()
    rows = []
    for label, scores, seat in GATE_LINE_GOLDEN_CASES:
        gaps = gate_line_potentials(scores, seat)
        status = gate_zone_status(scores, seat, advance)
        rows.append("  - {0}：四座积分（座位 0—3）=({1})；焦点座位={2}；inside_gap={3}；"
                    "outside_gap={4}；名次区间=[{5},{6}]（{7}）".format(
                        label, _gate_vector_text(scores), seat,
                        _gate_number(gaps["inside_gap"]),
                        _gate_number(gaps["outside_gap"]),
                        status["low"], status["high"], status["zone"]))
    for label, scores, seat, deltas in GATE_LINE_GOLDEN_RECOMPUTES:
        before = gate_line_potentials(scores, seat)
        moved = gate_line_delta_recomputed(scores, seat, deltas)
        after_vector = []
        for index in range(0, 4):
            after_vector.append(scores[index] + deltas[index])
        after = gate_line_values(after_vector)
        rows.append("  - {0}：四座积分（座位 0—3）=({1})；焦点座位={2}；"
                    "四座增量（座位 0—3）=({3})；本人增量 {4}；"
                    "inside_line {5}→{6}；outside_line {7}→{8}（移动={9}/{10}）；"
                    "Δinside_gap={11}；Δoutside_gap={12}".format(
                        label, _gate_vector_text(scores), seat, _gate_vector_text(deltas),
                        _gate_signed(deltas[seat]),
                        _gate_number(before["inside_line"]),
                        _gate_number(after["second"]),
                        _gate_number(before["outside_line"]),
                        _gate_number(after["third"]),
                        moved["inside_line_moved"], moved["outside_line_moved"],
                        _gate_signed(moved["delta_inside"]),
                        _gate_signed(moved["delta_outside"])))
    for label, scores, seat, own_delta in GATE_LINE_GOLDEN_FROZEN:
        before = gate_line_potentials(scores, seat)
        frozen = gate_line_delta_frozen_line(scores, seat, own_delta)
        rows.append("  - {0}：四座积分（座位 0—3）=({1})；焦点座位={2}；本人增量 {3}；"
                    "门线固定为动作前取值 {4}（移动={5}）；Δinside_gap={6}；"
                    "Δoutside_gap={7}".format(
                        label, _gate_vector_text(scores), seat, _gate_signed(own_delta),
                        _gate_number(before["inside_line"]),
                        frozen["inside_line_moved"],
                        _gate_signed(frozen["delta_inside"]),
                        _gate_signed(frozen["delta_outside"])))
    # E3：阶段账三概念（M1）与连续拐点（M2）金例追加在末尾（不改变既有行序）。
    rows.extend(stage_composition_golden_rows())
    rows.extend(gate_line_continuity_rows())
    return tuple(rows)


def gate_line_reference_source():
    """提示词里嵌入的参考实现原文（与金例测试核对的是同一份源码）。"""

    return "\n\n".join(inspect.getsource(fn).rstrip("\n") for fn in (
        gate_line_values, gate_line_potentials))


def gate_line_semantics_block():
    """门线口径块（进合同身份：改口径即改提示词身份，不沿用旧哈希）。"""

    advance, from_contract = gate_advance_count()
    indices = gate_line_indices(advance)
    source_note = ("（读自目标合同 {0}）".format(AV_GROUP_CONTRACT_RELPATH.name)
                   if from_contract else
                   "（目标合同不可读，缺省 {0}；一切以合同文件为准）".format(
                       GATE_ADVANCE_FALLBACK))
    return {
        "advance_count": advance,
        "advance_count_source": source_note,
        "order_statistic_mapping": ["升序下标 {0} = {1}".format(index, place)
                                    for index, place in GATE_ORDER_PLACES],
        "indices": indices,
        "inside_line": "晋级区末位门线（追第二名）= 升序下标 {0} 的分数".format(
            indices["inside_line_index"]),
        "outside_line": "区外头名门线（领先第三名）= 升序下标 {0} 的分数".format(
            indices["outside_line_index"]),
        "mode_names": {"recompute": "完整结算向量重算",
                       "frozen_line": "近似启发式（只加本人增量、门线固定）"},
        "forbidden_namings": list(GATE_LINE_FORBIDDEN_NAMINGS),
        "forbidden_claims": list(GATE_LINE_FORBIDDEN_CLAIMS),
        "clauses": list(gate_line_clauses()),
        "golden_rows": list(gate_line_golden_rows()),
        "reference_implementation": gate_line_reference_source(),
    }


# ============================================================ 1d. 作者守卫条款（未知 / 批次失败 / 修订行为差异）
#
# 来源：P4（M5 准入门禁）用修正后的判分器重判 R6 冻结批次的实测结论——r1 21/24、
# r2 20/24、admission_pass=false；根因两条都属**作者侧可预防**：
#   ① 未分析动作给 0.0，排在已知负分动作之前（实测 0.0 vs −17.8941 / −17.1687 /
#      −1.3883 / −17.5296，违反合同 output_contract.batch_failure_policy 原文）；
#   ② T07 的修订作答只改说明/注释，行为签名与父代逐项相同（无实质变更）。
# 本节把这两条写成作者可自查的条款（唯一口径来源，进合同身份），参考实现同样
# 写在受限子集内，可逐字复制成候选内的局部纯辅助函数。

#: 未知越位判据容差：与准入判分器当前实现同值（1e-12）；两处改动必须同步。
AUTHOR_UNKNOWN_TOLERANCE = 1e-12
#: 推荐的未分析动作下限余量（严格低于已知最低分，避开 action_key 决定次序）。
AUTHOR_UNKNOWN_MARGIN = 1.0


def action_has_produced_facts(action):
    """该动作是否有可评分的**已生产事实**（False = 未分析/缺证，不是已知 0）。

    事实口径同合同 scoring_view.fields.actions：动作后牌效事实、后续分支、
    条件路线、立即结算、家族进展任一存在即为已生产；fact_kind 为
    analysis_failed 且无其他事实时视为缺证（分析失败不产生可用读数）。
    """

    if action is None:
        return False
    for name in ("shanten_after", "standard_shanten_after",
                 "seven_pairs_shanten_after", "useful_tiles",
                 "immediate_settlement"):
        if action.get(name) is not None:
            return True
    for name in ("followup_branches", "routes", "family_progress_entries"):
        value = action.get(name)
        if value is not None and len(value) > 0:
            return True
    kind = action.get("fact_kind")
    if kind is None or kind == "analysis_failed":
        return False
    return True


def unknown_score_floor(known_scores):
    """已知评分的最低分；没有任何已知评分时返回 None（此时只能整批 ABSTAIN）。"""

    if known_scores is None:
        return None
    floor = None
    for item in known_scores:
        if item is None or item is True or item is False:
            continue
        value = float(item)
        if value - value != 0:
            continue
        if floor is None or value < floor:
            floor = value
    return floor


def guarded_unknown_score(known_scores, margin):
    """未分析动作的推荐取值：已知最低分 − margin（严格低于全部已知评分）。

    没有已知评分（窗口内没有任何动作带已生产事实）→ None：无合法取值，
    只能整批 ABSTAIN。margin 必须 > 0：等于 0 时次序由 action_key 决定，
    未知仍可能排在已知负分之前。
    """

    floor = unknown_score_floor(known_scores)
    if floor is None:
        return None
    if margin is None or margin is True or margin is False:
        return None
    step = float(margin)
    if step - step != 0 or step <= 0:
        return None
    return floor - step


def unknown_above_known_violations(entries, tolerance):
    """自查：列出「未知排在已知负分之前」的违规对（合同 batch_failure_policy）。

    entries：局部列表，每项 {"action_key": 字符串, "score": 有限数,
    "unknown": True/False}；unknown 由 action_has_produced_facts 决定。
    tolerance：判据容差，取 1e-12（提示词条款给出同一数值；本函数自带参数，
    复制到候选时无需外部常量）。
    判据与准入判分器一致：未分析分数 > 已知负分分数 + 容差 即违规；
    容差非法（None/布尔/非有限/负）返回 None——调用方必须按**未知**处理，
    不得把 None 当成「无违规」。
    """

    if tolerance is None or tolerance is True or tolerance is False:
        return None
    limit = float(tolerance)
    if limit - limit != 0 or limit < 0:
        return None
    violations = []
    for item in entries:
        if item.get("unknown") is not True:
            continue
        own = item.get("score")
        if own is None or own is True or own is False:
            continue
        own_value = float(own)
        if own_value - own_value != 0:
            continue
        for other in entries:
            if other.get("unknown") is True:
                continue
            known = other.get("score")
            if known is None or known is True or known is False:
                continue
            known_value = float(known)
            if known_value - known_value != 0:
                continue
            if known_value < 0 and own_value > known_value + limit:
                violations.append({"unknown": item.get("action_key"),
                                   "known": other.get("action_key"),
                                   "unknown_score": own_value,
                                   "known_score": known_value})
    return violations


#: 修订行为判定枚举：与准入判分器 sitin_model_admission.REVISION_* **逐字同值**——
#: 两处各写一套枚举就等于两套口径，这里只有一份（同源断言见
#: tools/test_sitin_generate_behavior_definition.py）。
BEHAVIOR_VERDICT_OBSERVED = "REVISION_OBSERVED"
BEHAVIOR_VERDICT_EQUIVALENT = "EQUIVALENT"
BEHAVIOR_VERDICT_PARENT_INCOMPATIBLE = "PARENT_MATERIAL_INCOMPATIBLE"
BEHAVIOR_VERDICT_CHILD_NO_EVIDENCE = "CHILD_NO_BEHAVIOR_EVIDENCE"
BEHAVIOR_VERDICTS: Tuple[str, ...] = (
    BEHAVIOR_VERDICT_OBSERVED, BEHAVIOR_VERDICT_EQUIVALENT,
    BEHAVIOR_VERDICT_PARENT_INCOMPATIBLE, BEHAVIOR_VERDICT_CHILD_NO_EVIDENCE,
)

#: 生产排序口径（**唯一**判定依据；生产实现是
#: hangma_bot.policy.action_value.batch_to_ranked_candidates）。
BEHAVIOR_ORDER_NOTE = (
    "生产排序 = 分数降序、同分按 action_key 升序、原始分数不先舍入"
    "（hangma_bot.policy.action_value.batch_to_ranked_candidates；"
    "准入判分器 preference_signature 复用同一实现同一口径）"
)

#: 等价形态（**不算**行为差异；准入不据此发放修订信用）：与复审 C1 逐条对应。
BEHAVIOR_EQUIVALENT_KINDS: Tuple[Tuple[str, str], ...] = (
    ("只改说明", "只改说明/注释/命名/trace 标签/不影响输出的常量：分值签名逐项相同"),
    ("保序平移", "所有动作分数 +c（c 为常数）：次序与首选动作都不变"),
    ("正比例缩放", "所有动作分数 ×c（c > 0）：次序与首选动作都不变"),
    ("只改非首选次序", "首选动作未变，只有其余动作的相对次序变化"),
)


def _behavior_table(entries, where: str):
    """[(action_key, score)] → {action_key: float}；None/空表 = 该侧无偏好证据（弃权）。

    非有限数（NaN/Inf）与布尔冒充数一律 ValueError（fail-closed）：自查不得用
    非法读数拼出一份「看起来合法」的行为报告。
    """

    if entries is None:
        return None
    table = {}
    for item in entries:
        key = str(item[0])
        raw = item[1]
        if raw is None or raw is True or raw is False:
            raise ValueError("{0} 的分数必须是有限数：{1!r}".format(where, raw))
        value = float(raw)
        if value - value != 0 or value in (float("inf"), float("-inf")):
            raise ValueError("{0} 的分数必须是有限数：{1!r}".format(where, raw))
        table[key] = value
    return table


def _preferred_from_table(table):
    """生产排序口径下的首选动作键；空表/None → None（无偏好证据）。"""

    best_key = None
    best_score = None
    for key in table:
        score = table[key]
        if best_score is None or score > best_score or (
                score == best_score and key < best_key):
            best_key = key
            best_score = score
    return best_key


def _order_from_table(table):
    """生产排序口径下的完整次序（元组；同分按 action_key 升序）。"""

    pairs = []
    for key in table:
        pairs.append((key, table[key]))
    pairs = sorted(pairs, key=lambda pair: (-pair[1], pair[0]))
    return tuple(pair[0] for pair in pairs)


def preferred_action_key(entries):
    """生产排序口径下的首选动作键（受限子集内可逐字复制；含平分按 action_key 升序）。

    entries：[(action_key, score)] 局部表；None 或空表 → None（该窗无偏好证据）。
    """

    if entries is None:
        return None
    best_key = None
    best_score = None
    for item in entries:
        key = str(item[0])
        score = float(item[1])
        if best_score is None or score > best_score or (
                score == best_score and key < best_key):
            best_key = key
            best_score = score
    return best_key


def behavior_change_summary(parent_entries, child_entries):
    """修订是否产生**可观察行为差异**（与准入同一口径的最小判定）。

    只认一件事：两侧都有可比评分且**生产排序的首选动作不同**。任一分值变化、
    保序平移、正比例缩放、只改非首选次序、只改说明都**不算**行为差异。
    """

    parent_top = preferred_action_key(parent_entries)
    child_top = preferred_action_key(child_entries)
    changed = (parent_top is not None and child_top is not None
               and parent_top != child_top)
    return {"changed": changed, "parent_top": parent_top, "child_top": child_top}


def behavior_change_report(parent_entries, child_entries):
    """修订自查（**与生产排序和准入判分同一口径**）：四项读数 + 唯一判定。

    parent_entries / child_entries：同一冻结可见窗口上的 [(action_key, score)]
    二元组局部表（函数内部按 action_key 归并）；None 或空表表示该侧**弃权/无偏好证据**。

    返回（键名与含义固定）：
      changed             唯一判定：verdict == REVISION_OBSERVED
      verdict             四态：REVISION_OBSERVED / EQUIVALENT /
                          PARENT_MATERIAL_INCOMPATIBLE / CHILD_NO_BEHAVIOR_EVIDENCE
      ① value_diff_count  分值变化项数（**不单独构成行为差异**）
      ② order_changed     排序是否变化（含非首选；**不单独构成行为差异**）
         order_changed_pairs 次序反转对数（并列被打破不算反转）
      ③ top_changed       最终首选动作是否变化（**唯一**能证明行为差异的读数）
         parent_top / child_top 两侧首选动作键（None = 该侧弃权）
      ④ parent_observable / child_observable / abstain_mask 弃权/未知掩码
      removed_keys / added_keys 键集合变化
      equivalence_reason  判为无差异时的原因（只改说明/保序平移/正比例缩放/只改非首选次序）

    为什么必须这样：复审 R9-P25 C1·P1——旧的「任一分值改变即行为变化」把**保序平移与
    正比例缩放**当成了修订能力，与准入合同（首选动作有可观察差异）相反；题面写
    「只改分值不改次序：有行为差异=True」正是这条假阳性。
    """

    parent = _behavior_table(parent_entries, "parent_entries")
    child = _behavior_table(child_entries, "child_entries")
    parent = parent or {}
    child = child or {}
    parent_observable = bool(parent)
    child_observable = bool(child)
    value_diff = 0
    removed = 0
    added = 0
    for key in parent:
        if key not in child:
            removed += 1
        elif child[key] != parent[key]:
            value_diff += 1
    for key in child:
        if key not in parent:
            added += 1
    parent_top = _preferred_from_table(parent)
    child_top = _preferred_from_table(child)
    parent_order = _order_from_table(parent)
    child_order = _order_from_table(child)
    order_changed = parent_order != child_order
    top_changed = parent_top != child_top
    if not parent_observable:
        verdict = BEHAVIOR_VERDICT_PARENT_INCOMPATIBLE
    elif not child_observable:
        verdict = BEHAVIOR_VERDICT_CHILD_NO_EVIDENCE
    elif top_changed:
        verdict = BEHAVIOR_VERDICT_OBSERVED
    else:
        verdict = BEHAVIOR_VERDICT_EQUIVALENT
    reason = ""
    if verdict == BEHAVIOR_VERDICT_EQUIVALENT:
        if order_changed:
            reason = "只改非首选次序：首选动作未变（准入同一口径不发放修订信用）"
        elif value_diff == 0 and removed == 0 and added == 0:
            reason = "只改说明：分值签名逐项相同（注释/命名/不影响输出的常量）"
        else:
            reason = "保序变换：分值变化但次序与首选动作都未变（统一平移/正比例缩放在此列）"
    elif verdict == BEHAVIOR_VERDICT_CHILD_NO_EVIDENCE:
        reason = "子代在该窗没有可比评分（弃权/执行失败）：不算选择差异，也不兑换修订信用"
    elif verdict == BEHAVIOR_VERDICT_PARENT_INCOMPATIBLE:
        reason = "父代在该窗没有可比评分：材料不兼容，不判候选挂也不发放信用"
    else:
        reason = "首选动作改变：{0} → {1}".format(parent_top, child_top)
    return {
        "changed": verdict == BEHAVIOR_VERDICT_OBSERVED,
        "verdict": verdict,
        "order_note": BEHAVIOR_ORDER_NOTE,
        "value_diff_count": value_diff,
        "order_changed": order_changed,
        "order_changed_pairs": len(order_reversal_pairs(parent_entries or (),
                                                        child_entries or ())),
        "top_changed": top_changed,
        "parent_top": parent_top,
        "child_top": child_top,
        "parent_observable": parent_observable,
        "child_observable": child_observable,
        "abstain_mask": {"parent": not parent_observable,
                         "child": not child_observable},
        "removed_keys": removed,
        "added_keys": added,
        "equivalence_reason": reason,
    }


def order_reversal_pairs(parent_entries, child_entries):
    """次序反转对（供 changed_branches 逐条声明）；并列被打破不算反转。

    parent_entries / child_entries 形状同 behavior_change_report：[(action_key, score)]。
    """

    parent = {}
    for item in parent_entries:
        parent[str(item[0])] = float(item[1])
    child = {}
    for item in child_entries:
        child[str(item[0])] = float(item[1])
    shared = []
    for key in parent:
        if key in child:
            shared.append(key)
    shared = sorted(shared)
    pairs = []
    for index in range(0, len(shared)):
        for other in range(index + 1, len(shared)):
            first = shared[index]
            second = shared[other]
            before = parent[first] - parent[second]
            after = child[first] - child[second]
            if before == 0 or after == 0:
                continue
            if before > 0 and after < 0:
                pairs.append((first, second))
            elif before < 0 and after > 0:
                pairs.append((first, second))
    return tuple(pairs)


# —— 提示词里的实测金例（值由上面的参考实现算出，不手抄）——

#: 未知越位实测形态：(标签, 未分析键, 未分析分数, 已知负分键, 已知负分分数)。
AUTHOR_UNKNOWN_GOLDEN = (
    ("R6 r1/T07 实测", "discard:2b", 0.0, "discard:1w", -17.8941),
    ("R6 r2/T05 实测", "discard:2b", 0.0, "discard:1w", -1.3883),
    ("内置种子（对照，满足）", "discard:2b", -5.5, "discard:1w", -4.5),
)
#: 修订行为差异金例：(标签, 父代 [(键, 分)], 子代 [(键, 分)])。
#: 五条控制用例由 behavior_change_report 现算（题面与金例测试同源）：
#: 平移 / 缩放 / 只改非首选次序 / 平分破除 / 真实首选改变 + R6 T07 的「只改说明」形态。
AUTHOR_BEHAVIOR_GOLDEN = (
    ("只改说明（R6 T07 实测形态）", (("discard:1w", 5.0), ("discard:2b", -3.0)),
     (("discard:1w", 5.0), ("discard:2b", -3.0))),
    ("保序平移（全体 +100，只改分值不改次序）",
     (("discard:1w", 5.0), ("discard:2b", -3.0)),
     (("discard:1w", 105.0), ("discard:2b", 97.0))),
    ("正比例缩放（全体 ×3）", (("discard:1w", 5.0), ("discard:2b", -3.0)),
     (("discard:1w", 15.0), ("discard:2b", -9.0))),
    ("只改非首选次序", (("discard:9b", 5.0), ("discard:1w", 1.0), ("discard:2b", 2.0)),
     (("discard:9b", 5.0), ("discard:1w", 3.0), ("discard:2b", 1.0))),
    ("平分破除（并列 → 真首选改选）",
     (("discard:1w", 5.0), ("discard:2b", 5.0)),
     (("discard:1w", 5.0), ("discard:2b", 6.0))),
    ("真实首选改变（次序反转）", (("discard:1w", 5.0), ("discard:2b", -3.0)),
     (("discard:1w", -3.0), ("discard:2b", 5.0))),
)


def author_guard_clauses():
    """作者守卫条款（唯一口径）：未知取值 / 批次失败与部分失败 / 修订行为差异。"""

    floor_example = guarded_unknown_score([-17.8941, -3.2, 12.0], AUTHOR_UNKNOWN_MARGIN)
    return (
        "【未知 ≠ 0】一个动作在本窗口没有任何已生产事实（动作后牌效事实、后续分支、"
        "条件路线、立即结算、家族进展全缺，含 fact_kind=analysis_failed 且无其他事实）时，"
        "它的读数是**未知**，不是 0；0.0 表示「已知中性（已算出相等）」。"
        "禁止用 0.0（或任何不受下式约束的有限数）给未分析动作评分。",
        "【未知不得越位】（合同 output_contract.batch_failure_policy 原文）"
        "未分析动作的分数必须 ≤ 本窗口已知负分动作的最低分（容差 {0:g}），"
        "否则视为「未知自动排在已知负分之前」，整批判挂。".format(AUTHOR_UNKNOWN_TOLERANCE),
        "【未知的唯一合法取值】二选一，并在机制说明里写明用了哪一种："
        "① 整批 ABSTAIN 加非空 reason（窗口内没有任何动作带已生产事实时**只能**这样）；"
        "② SCORED 时取「已知最低分 − margin」（margin > 0，例如 {0:g}）——"
        "本窗口示例：已知最低分 −17.8941 ⇒ 未分析动作取 {1:g}。".format(
            AUTHOR_UNKNOWN_MARGIN, floor_example),
        "【为什么必须严格更低】判据用容差，是「不高于」；但分数相等时次序由 action_key "
        "决定，未分析动作仍可能排在已知负分之前，故推荐写法取严格更低。"
        "该取值只能记成「未知取值」，不得记成「已知为 0」。",
        "【批次失败与部分失败】（合同 output_contract 原文）SCORED 必须对输入**全部**动作"
        "恰好一项、全部有限数、无遗漏/重复/越界键；抛异常、非有限数（NaN/Inf）、布尔冒充数、"
        "漏键或重复键、越界键、超工作量限额、缺必需字段——任一项即**整窗口失效**，"
        "由骨架降级到已备合法紧急计划：候选不得吞掉失败、不得悄悄拼 V2 分数、"
        "不得把失败伪装成 SCORED。",
        "【缺证不得冒充已评分】ABSTAIN 时 entries 必须为空（不得部分成功后用 0 补齐）；"
        "SCORED 时缺证动作的分数只能按上一条写法给出，且 trace 必须列出缺项"
        "（unknown_facts/unknown_policy），不得把它的数值写进「已评分分项」，"
        "也不得把缺证批次的结论当成已评分结论。",
        "【M1 修订必须产生行为差异——唯一判定口径】判据只有一条，且与准入判分器"
        "**同一枚举同一实现来源**：在冻结可见窗口上两侧都有可比评分（SCORED 且有条目），"
        "且**生产排序的首选动作不同**（生产排序 = 分数降序、同分按 action_key 升序、"
        "原始分数不先舍入，即 batch_to_ranked_candidates）。首选动作相同 ⇒ 无行为差异，"
        "本次修订不该提交。",
        "【什么不算行为差异（准入不发放修订信用）】① 保序平移：所有动作分数 +c；"
        "② 正比例缩放：所有动作分数 ×c（c > 0）；③ 只改非首选次序：首选动作未变，"
        "只是其余动作的相对次序变了；④ 只改说明/注释/命名/trace 标签/不影响输出的常量。"
        "**任一分值改变都不是行为变化**——评分签名与行为签名是两回事，"
        "「只改分值不改次序」必须记为**没有**行为差异。",
        "【平分破除按生产排序】同分不是「并列都算第一」：生产排序在同分时取 action_key "
        "升序的第一个。父代并列、子代分出胜负（或反向）时，若**首选动作因此改变**即算"
        "行为差异；若首选未变（例如并列只出现在非首选位置）不算。",
        "【一侧弃权不算选择差异】父代或子代在该窗没有可比评分（ABSTAIN/执行失败）时："
        "既不算行为差异，也不得把「与父代不同」当修订能力（准入分别判 "
        "PARENT_MATERIAL_INCOMPATIBLE / CHILD_NO_BEHAVIOR_EVIDENCE，不发放信用）。",
        "【M1 自查指令（必须写进回复）】在 changed_branches 里逐条写出「窗口类 + 动作键 + "
        "差异级别」，并**分别报告四项读数**：① 分值变化项数；② 排序是否变化；"
        "③ 最终首选动作（父代 → 子代；次序反转是它的典型形态）；"
        "④ 弃权/未知掩码（该窗两侧是否都取得可比评分）。"
        "四项里**只有 ③ 能证明行为差异**；写不出 ③ 就说明本次修订无实质变更，"
        "必须重新设计而不是改措辞。",
        "【不得夸大差异】首选动作未变时，changed_branches 不得写「改变了动作排序」或"
        "「改变了首选」；expected_direction 必须与所列差异一致；把「未知越位」修好本身"
        "就是一个合法的差异来源（未分析动作由 0.0 改为低于已知最低分），但它只有在"
        "**首选动作随之改变**时才构成行为差异，应在 changed_branches 里点名二者。",
    )


def author_guard_golden_rows():
    """守卫金例行文本：全部由参考实现算出（提示词与金例测试同源）。"""

    rows = []
    for label, unknown_key, unknown_score, known_key, known_score in AUTHOR_UNKNOWN_GOLDEN:
        entries = ({"action_key": unknown_key, "score": unknown_score, "unknown": True},
                   {"action_key": known_key, "score": known_score, "unknown": False})
        found = unknown_above_known_violations(entries, AUTHOR_UNKNOWN_TOLERANCE)
        rows.append("  - {0}：未分析 {1}={2:g} vs 已知负分 {3}={4:g} ⇒ 违规 {5} 对".format(
            label, unknown_key, unknown_score, known_key, known_score, len(found)))
    floor_value = guarded_unknown_score([-17.8941, -3.2, 12.0], AUTHOR_UNKNOWN_MARGIN)
    rows.append("  - 合规写法（推荐）：已知最低分 −17.8941 − margin {0:g} ⇒ 未分析动作取 {1:g}"
                "（严格低于全部已知评分，违规 0 对）".format(
                    AUTHOR_UNKNOWN_MARGIN, floor_value))
    rows.append("  - 无已知评分：known_scores 为空 ⇒ 无合法取值（guarded_unknown_score → None），"
                "只能整批 ABSTAIN，不得给 0.0")
    for label, parent, child in AUTHOR_BEHAVIOR_GOLDEN:
        report = behavior_change_report(parent, child)
        rows.append(
            "  - 修订自查（{0}）：有行为差异={1}；判定={2}；①分值差异 {3} 项；"
            "②排序变化={4}；③首选 {5}→{6}；④弃权掩码 父={7}/子={8}".format(
                label, report["changed"], report["verdict"],
                report["value_diff_count"], report["order_changed"],
                report["parent_top"], report["child_top"],
                report["abstain_mask"]["parent"], report["abstain_mask"]["child"]))
    return tuple(rows)


def author_guard_reference_source():
    """提示词里嵌入的守卫参考实现（与金例测试核对的是同一份源码）。"""

    return "\n\n".join(inspect.getsource(fn).rstrip("\n") for fn in (
        unknown_score_floor, guarded_unknown_score, unknown_above_known_violations,
        preferred_action_key, behavior_change_summary))


def author_guard_semantics_block():
    """作者守卫条款块（进合同身份：改条款即改提示词身份，旧 attempt 不复用）。"""

    return {
        # /2（R9 P25 包 A · 复审 C1）：修订行为判定由「任一分值变化」改为
        # 「两侧都有可比评分且**生产排序的首选动作**不同」，与准入同一枚举同一口径；
        # 条款、金例与参考实现同源更新——schema 升版即提示词身份变化（旧 attempt 不复用）。
        "schema": "sitin-author-guard/2",
        "unknown_tolerance": AUTHOR_UNKNOWN_TOLERANCE,
        "unknown_margin": AUTHOR_UNKNOWN_MARGIN,
        "behavior_verdicts": list(BEHAVIOR_VERDICTS),
        "behavior_order_note": BEHAVIOR_ORDER_NOTE,
        "behavior_equivalent_kinds": [list(item) for item in BEHAVIOR_EQUIVALENT_KINDS],
        "clauses": list(author_guard_clauses()),
        "golden_rows": list(author_guard_golden_rows()),
        "failure_source": ("未知越位：contracts/action-value-v1.json output_contract"
                           ".batch_failure_conditions / batch_failure_policy（原文）；"
                           "修订行为差异：生产排序 batch_to_ranked_candidates + 准入"
                           " preference_signature / revision_behavior_delta（同一枚举）"),
        "reference_implementation": author_guard_reference_source(),
    }


# ---------------------------------------------------------------------------
# 受限子集静态规则（AV-SUB）：contracts/action-value-v1.json
# restricted_subset.rules 是唯一来源，题面渲染与预检诊断共用同一份读法
# ---------------------------------------------------------------------------

def normalize_subset_rules(raw_rules) -> List[Dict[str, Any]]:
    """合同 restricted_subset.rules → 规范化清单（缺项/畸形一律 fail-closed）。

    这是**唯一**读规则的地方：题面渲染（生成题与修复题）与预检诊断都从这里
    取数，不在 Python 里另写一套约束文案、也不另立一张消息→编号表。
    """

    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError(
            "合同 restricted_subset.rules 缺失或为空：静态规则清单必须由合同渲染"
            "（拒绝在代码里另写一套约束文案，fail-closed）")
    normalized: List[Dict[str, Any]] = []
    seen: set = set()
    for item in raw_rules:
        if not isinstance(item, Mapping):
            raise ValueError("restricted_subset.rules 条目必须是对象：{0!r}".format(item))
        rule_id = str(item.get("id") or "").strip()
        statement = str(item.get("statement") or "").strip()
        pattern = str(item.get("message_pattern") or "")
        if not rule_id or not statement or not pattern:
            raise ValueError(
                "restricted_subset.rules 条目缺 id/statement/message_pattern：{0!r}".format(item))
        if rule_id in seen:
            raise ValueError("restricted_subset.rules 编号重复：{0}".format(rule_id))
        seen.add(rule_id)
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError("restricted_subset.rules[{0}] 的 message_pattern 不可编译：{1}"
                             .format(rule_id, exc)) from exc
        applies = [str(target) for target in (item.get("applies_to") or [])]
        for target in applies:
            if target not in AV_SUBSET_RULE_TARGETS:
                raise ValueError("restricted_subset.rules[{0}].applies_to 含未知题类 {1!r}"
                                 .format(rule_id, target))
        normalized.append({
            "id": rule_id,
            "statement": statement,
            "applies_to": applies,
            "message_pattern": pattern,
            "reachable": bool(item.get("reachable", True)),
        })
    return normalized


def subset_rules_for_target(rules, target: str) -> List[Dict[str, Any]]:
    """按题类过滤规则（applies_to 含该题类即入选；不改变任何判据）。"""

    if target not in AV_SUBSET_RULE_TARGETS:
        raise ValueError("未知题类 {0!r}；闭集 {1}".format(target, AV_SUBSET_RULE_TARGETS))
    return [rule for rule in (rules or []) if target in (rule.get("applies_to") or [])]


def render_restricted_subset_rule_lines(rules, target: str) -> List[str]:
    """把合同规则渲染成候选可读的题面片段（题类过滤 + 逐条稳定编号）。

    渲染文本里的约束句**逐字**来自合同 statement；这里只加编号与格式，
    因此"改合同一句 ⇒ 提示词即变"，不存在第二套文案可漂移（同源测试断言）。
    """

    selected = subset_rules_for_target(rules, target)
    if not selected:
        return ["", "【受限子集静态规则（AV-SUB）】",
                "  - 合同未声明适用于 {0} 的 restricted_subset.rules 条目：本提示词"
                "缺少静态规则清单，属装配缺陷（fail-closed，不得读成「没有约束」）。"
                .format(target)]
    lines = ["", "【受限子集静态规则（AV-SUB；与执行器同一份定义渲染；违反即拒绝装载，"
                 "不进入执行）】",
             "  - 编号稳定：预检失败信息会给出命中的 AV-SUB 编号，按编号回查本节即可；"
             "本节条目与执行器静态检查逐条同源，不是另写的一套说明。",
             "  - 适用题类 {0}，共 {1} 条：".format(target, len(selected))]
    for rule in selected:
        lines.append("  - {0}：{1}".format(rule["id"], rule["statement"]))
    return lines


def subset_rule_hits(message: str, rules=None) -> List[Dict[str, str]]:
    """执行器拒绝消息 → 命中的规则（编号 + 候选可读约束）。

    匹配方式：规则目录的 message_pattern 对执行器原话做 re.fullmatch；命中不到即
    返回空列表（**不猜**：宁可 unmapped，也不把某条规则硬套上去）。
    """

    if rules is None:
        rules, _digest = load_action_value_subset_rules()
    hits: List[Dict[str, str]] = []
    for rule in rules:
        if re.fullmatch(rule["message_pattern"], message, re.DOTALL):
            hits.append({"id": rule["id"], "statement": rule["statement"]})
    return hits


def match_subset_rule_ids(message: str, rules=None) -> List[str]:
    """命中规则的编号列表（subset_rule_hits 的薄封装）。"""

    return [hit["id"] for hit in subset_rule_hits(message, rules)]


# ---------------------------------------------------------------------------
# 公开接口附录（C5）：contracts/action-value-public-interface-v1.json 是唯一来源
# ---------------------------------------------------------------------------
# 复审 R9-P25 C5·P1：静态规则已披露，但**真实输入字段与输出类型仍不完整**——T05/T09
# 题面只有概述，作者读不到 action_value.py 实际投影的动作字段（followup_branches /
# shanten_after / standard_shanten_after / seven_pairs_shanten_after / useful_tiles /
# family_progress），于是去猜字段名（r1/T09 读了不存在的 normal_progress /
# seven_pairs_progress），可解窗因此弃权；输出侧也没写清 SCORED.reason 的三态与空串禁则。
# 本节把附录做成**与 60 条静态规则同一机制**：兄弟文件 → 规范化（fail-closed）→
# 生成题与修复题同一份渲染；附录里的类型/形状声明由
# tools/test_sitin_generate_public_interface.py 用真实投影逐路径检验，禁止照抄后自称一致。

#: 附录每条路径必须机器可读的字段：路径、类型、容器形状、单位、投影来源函数。
AV_PUBLIC_INTERFACE_REQUIRED_PATH_FIELDS: Tuple[str, ...] = (
    "path", "types", "shape", "unit", "source",
)
#: 允许声明的 Python 类型名（观察侧用 type(value).__name__，None 记 NoneType）。
#: 不在表内即装配缺陷：附录不得用「其它」「任意」这类不可检验的说法。
AV_PUBLIC_INTERFACE_TYPE_NAMES: Tuple[str, ...] = (
    "str", "int", "float", "bool", "dict", "tuple", "list", "NoneType",
)

_AV_PUBLIC_INTERFACE_CACHE: Dict[str, Any] = {}


def normalize_public_interface(payload) -> Dict[str, Any]:
    """附录 JSON → 规范化载荷（缺项/畸形/重复路径一律 fail-closed）。

    与 normalize_subset_rules 同一纪律：这是**唯一**读附录的地方，渲染、身份与
    一致性检验都从这里取数；缺表时抛 ValueError（不从缺表读成「没有接口约束」）。
    """

    if not isinstance(payload, Mapping):
        raise ValueError("公开接口附录必须是 JSON 对象")
    paths = payload.get("paths")
    if not isinstance(paths, list) or not paths:
        raise ValueError("公开接口附录 paths 缺失或为空（fail-closed）")
    normalized: List[Dict[str, Any]] = []
    seen: set = set()
    for item in paths:
        if not isinstance(item, Mapping):
            raise ValueError("公开接口附录 paths 条目必须是对象：{0!r}".format(item))
        entry: Dict[str, Any] = {}
        for name in AV_PUBLIC_INTERFACE_REQUIRED_PATH_FIELDS:
            value = item.get(name)
            if name == "types":
                if not isinstance(value, list) or not value:
                    raise ValueError("附录 {0} 的 types 必须是非空列表".format(item.get("path")))
                for type_name in value:
                    if type_name not in AV_PUBLIC_INTERFACE_TYPE_NAMES:
                        raise ValueError(
                            "附录 {0} 声明了不可检验的类型名 {1!r}（闭集 {2}）".format(
                                item.get("path"), type_name, AV_PUBLIC_INTERFACE_TYPE_NAMES))
                entry[name] = [str(type_name) for type_name in value]
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError("附录 {0} 缺字段 {1}".format(item.get("path"), name))
            entry[name] = value
        path = entry["path"]
        if path in seen:
            raise ValueError("公开接口附录路径重复：{0}".format(path))
        seen.add(path)
        for optional in ("enum", "element_types", "note", "null_when"):
            value = item.get(optional)
            if value is None:
                continue
            if optional == "enum":
                if not isinstance(value, list) or not value:
                    raise ValueError("附录 {0} 的 enum 必须是非空列表".format(path))
                entry[optional] = [str(member) for member in value]
            elif optional == "element_types":
                if not isinstance(value, list) or not value:
                    raise ValueError("附录 {0} 的 element_types 必须是非空列表".format(path))
                for type_name in value:
                    if type_name not in AV_PUBLIC_INTERFACE_TYPE_NAMES:
                        raise ValueError(
                            "附录 {0} 的 element_types 含不可检验的类型名 {1!r}".format(
                                path, type_name))
                entry[optional] = [str(member) for member in value]
            else:
                entry[optional] = str(value)
        normalized.append(entry)
    view_api = payload.get("view_api")
    if not isinstance(view_api, list) or not view_api:
        raise ValueError("公开接口附录 view_api 缺失或为空（fail-closed）")
    output_contract = payload.get("output_contract")
    if not isinstance(output_contract, Mapping):
        raise ValueError("公开接口附录 output_contract 缺失（fail-closed）")
    examples = payload.get("examples")
    if not isinstance(examples, Mapping) or "outputs" not in examples:
        raise ValueError("公开接口附录 examples 缺失（fail-closed）")
    applies = [str(target) for target in (payload.get("applies_to") or [])]
    if not applies:
        raise ValueError("公开接口附录 applies_to 为空（必须显式声明适用题类）")
    for target in applies:
        if target not in AV_SUBSET_RULE_TARGETS:
            raise ValueError("公开接口附录 applies_to 含未知题类 {0!r}".format(target))
    return {
        "schema": payload.get("schema"),
        "appendix_id": payload.get("appendix_id"),
        "version": payload.get("version"),
        "applies_to": applies,
        "purpose": payload.get("purpose"),
        "identity_note": payload.get("identity_note"),
        "source_of_truth": dict(payload.get("source_of_truth") or {}),
        "conventions": [str(item) for item in (payload.get("conventions") or [])],
        "paths": normalized,
        "view_api": [dict(item) for item in view_api],
        "output_contract": dict(output_contract),
        "examples": dict(examples),
    }


def load_action_value_public_interface(path=None):
    """读公开接口附录（兄弟文件）；返回 (规范化附录, 文件 sha256)。

    与 load_action_value_subset_rules 同一纪律：唯一来源、按路径缓存、渲染与检验共用。
    """

    target = Path(path) if path is not None else (_project_file(_PROJECT_ROOT, REPO / AV_PUBLIC_INTERFACE_RELPATH))
    key = str(target)
    if key not in _AV_PUBLIC_INTERFACE_CACHE:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        _AV_PUBLIC_INTERFACE_CACHE[key] = (
            normalize_public_interface(payload), hashlib.sha256(raw).hexdigest())
    return _AV_PUBLIC_INTERFACE_CACHE[key]


def _appendix_path_line(entry, *, skip_note: bool = False) -> str:
    """一条路径的渲染文本（**全部**来自附录字段，不存在第二套文案）。

    skip_note=True 时省略该条的 note——只用在"同一字段组内 note 逐字相同"的场合：
    此时 note 由组头渲染一次，路径行不再重复，文本一字未改（卡面瘦身只做去重）。
    """

    parts = ["{0}：{1}".format(entry["path"], entry["shape"])]
    if entry.get("unit"):
        parts.append(entry["unit"])
    if entry.get("enum"):
        parts.append("枚举 " + "/".join(entry["enum"]))
    if entry.get("null_when"):
        parts.append("None=" + entry["null_when"])
    if entry.get("note") and not skip_note:
        parts.append(entry["note"])
    return "  - " + "；".join(parts)


def render_public_interface_lines(target: str, appendix=None) -> List[str]:
    """把公开接口附录渲染成题面片段（生成题与修复题同一份来源，按 applies_to 过滤）。

    渲染文本里的类型/形状/单位/枚举/可空条件**逐字**来自附录字段；这里只加编号与
    格式，因此「改附录一个字段 ⇒ 两类题面同时变」，不存在可漂移的第二套说明。
    缺附录、缺题类或缺关键块一律显式报缺（fail-closed），不静默当成「没有接口约束」。
    """

    if target not in AV_SUBSET_RULE_TARGETS:
        raise ValueError("未知题类 {0!r}；闭集 {1}".format(target, AV_SUBSET_RULE_TARGETS))
    if appendix is None:
        appendix, _digest = load_action_value_public_interface()
    applies = appendix.get("applies_to") or []
    if target not in applies:
        return ["", "【公开接口附录（{0}）】".format(appendix.get("appendix_id")),
                "  - 附录未声明适用于 {0}：本提示词缺少公开输入合同，属装配缺陷"
                "（fail-closed，不得读成「没有接口约束」）。".format(target)]
    lines = ["", "【公开接口附录（{0}；逐字段=实际投影，不是概述）】".format(
        appendix.get("appendix_id"))]
    source = appendix.get("source_of_truth") or {}
    lines.append("  - 来源：{0} 的 {1}（schema={2}）；与 contracts/action-value-v1.json "
                 "分开存放，不进合同字节身份。".format(
                     source.get("projection_module"), source.get("projection_call"),
                     source.get("schema_version_value")))
    lines.append("  - 投影函数：{0}".format("、".join(source.get("projection_functions") or ())))
    for index, item in enumerate(appendix.get("conventions") or (), start=1):
        lines.append("  - 记法 {0}：{1}".format(index, item))
    lines.append("  - 字段清单（共 {0} 条；actions[] = 动作表逐项）：".format(
        len(appendix["paths"])))
    for entry in appendix["paths"]:
        lines.append(_appendix_path_line(entry))
    lines.append("  - ScoringView 只读访问器实际形状：")
    for item in appendix["view_api"]:
        lines.append("  - {0} → {1}：{2}".format(item.get("name"), item.get("returns"),
                                                 item.get("note")))
    contract = appendix["output_contract"]
    lines.append("  - 输出：status 只能是 " + "/".join(contract.get("status_values") or ()))
    lines.append("  - SCORED：" + str(contract.get("scored")))
    lines.append("  - ABSTAIN：" + str(contract.get("abstain")))
    forms = contract.get("reason_three_forms") or []
    lines.append("  - reason 的三种合法形态：" + "；".join(str(item) for item in forms))
    lines.append("  - reason 空字符串：" + str(contract.get("reason_empty_string_rejected")))
    lines.append("  - 未知 ≠ 0：" + str(contract.get("unknown_is_not_zero")))
    lines.append("  - 整批失败：" + str(contract.get("batch_failure")))
    examples = appendix.get("examples") or {}
    if examples.get("input") is not None:
        lines.append("  - 最小合法输入（真实投影的 candidate_view，逐字节检验）：")
        for line in json.dumps(examples["input"], ensure_ascii=False, sort_keys=True,
                               indent=1).splitlines():
            lines.append("    " + line)
    outputs = examples.get("outputs") or []
    if outputs:
        lines.append("  - 合法/不合法输出范例（前两条合法；第三条必须整批失败）：")
        for index, item in enumerate(outputs, start=1):
            lines.append("    {0}) {1}".format(index, item.get("label")))
            lines.append("       " + json.dumps(item.get("value"), ensure_ascii=False,
                                                sort_keys=True))
    return lines


def public_interface_identity(appendix, digest: str) -> Dict[str, str]:
    """附录进提示词身份的记法（路径 + sha256；改一个字节即改提示词身份）。"""

    return {"path": str(AV_PUBLIC_INTERFACE_RELPATH), "sha256": digest,
            "appendix_id": str(appendix.get("appendix_id"))}


def render_action_value_task_contract(*, objective_summary: str,
                                      panel_boundary: str,
                                      prompt_role: str,
                                      parent=None,
                                      feedback=None,
                                      budget_note: str = "") -> Dict[str, Any]:
    """渲染 action_value_v1 的 TaskContract（§10 清单逐条）。

    白名单/限额/禁令/输出合同/入口签名/视图字段全部**原样取自**
    contracts/action-value-v1.json；本函数不复制任何数值。M1 附父代
    原始源码+完整身份+三段开发反馈；I1 不附伪造成绩（feedback 恒 None）。
    """

    contract, digest = load_action_value_contract()
    # 规则目录来自兄弟文件（不进合同身份）；缺文件/缺表即 ValueError（fail-closed）。
    _subset_rules, _subset_rules_sha = load_action_value_subset_rules()
    # 公开接口附录同样来自兄弟文件；缺文件/缺块即 ValueError（fail-closed）。
    _public_interface, _public_interface_sha = load_action_value_public_interface()
    entry = contract["entry_point"]
    scoring_view = contract["scoring_view"]
    output_contract = contract["output_contract"]
    subset = contract["restricted_subset"]
    limits = contract["limits"]
    whitelist = contract["whitelist"]
    identity = contract.get("identity") or {}
    payload = {
        "schema": AV_TASK_CONTRACT_SCHEMA,
        "candidate_kind": contract.get("candidate_kind", AV_CANDIDATE_KIND),
        "contract_id": contract.get("contract_id"),
        "contract_sha256": digest,
        # §10-1：本批目标、工程面板边界、终端 U 与当前可见赛事信息。
        "objective": {
            "summary": objective_summary,
            "terminal_utility": default_objective_summary(),
            "note": "终端 U 的精确定义见目标合同 group-dev-v1.json；"
                    "大牌次数、改选率、评分器自报价值都不是替代目标",
        },
        "panel_boundary": panel_boundary,
        "prompt_role": prompt_role,
        # §10-2：score_actions 完整签名/字段含义单位可空/工具目录/数值与工作量限制。
        "entry_point": {
            "signature": entry["signature"],
            "docstring": entry["docstring"],
            "hu_mode": entry["hu_mode"],
            "hu_mode_note": entry["hu_mode_note"],
            "rank_contract": entry["rank_contract"],
        },
        "scoring_view": {
            "schema_version": scoring_view["schema_version"],
            "fields": scoring_view["fields"],
            # P11/P10c：可用赛事基准必须进提示词（否则「合同新增字段不进渲染器」，
            # 候选读不到阶段账 = M1 的最终价值落空）。缺键时为 None → 渲染端 fail-closed。
            "competition_bases": scoring_view.get("competition_bases"),
            "route_states": scoring_view["route_states"],
            "progress_states": scoring_view["progress_states"],
            "route_progress_note": scoring_view["route_progress_note"],
        },
        "tool_catalog": {
            "builtins": whitelist["builtins"],
            "builtin_notes": whitelist["builtin_notes"],
            "methods_readonly": whitelist["methods_readonly"],
            "operators": whitelist["operators"],
            "modules": whitelist["modules"],
            "modules_note": whitelist["modules_note"],
            "view_api": whitelist["view_api"],
        },
        "limits": {
            "rule_analysis": limits["rule_analysis"],
            "candidate": limits["candidate"],
        },
        "metering_rules": limits["metering_rules"],
        "limits_escalation": limits["escalation"],
        # §10-3：候选负责完整动作取舍；不修改规则、接口、评估器或运行配置。
        "responsibility": {
            "candidate_owns": "候选内部对全部合法动作的完整取舍（含胡与继续的比较）",
            "candidate_must_not": subset["forbidden"] + [
                "不修改规则、接口、评估器或运行配置",
                "不自行判定实验优胜或发布",
            ],
            "subset_allowed": subset["allowed"],
            "enforcement": subset["enforcement"],
            "subset_note": subset["note"],
        },
        # §10-6：受限子集静态规则清单（兄弟文件 action-value-restricted-rules-v1.json）。
        # 生成题与修复题读同一份定义；缺表即 fail-closed（见 normalize_subset_rules）。
        # 规则目录的 sha 只进**本 payload 身份**（提示词血缘），不进合同 sha256。
        "subset_rules": _subset_rules,
        "subset_rules_source": {"path": str(AV_SUBSET_RULES_RELPATH),
                                "sha256": _subset_rules_sha},
        # §C5：公开接口附录（兄弟文件 action-value-public-interface-v1.json）。
        # 生成题与修复题读同一份定义；缺表即 fail-closed（见 normalize_public_interface）。
        # 附录 sha 只进**本 payload 身份**（提示词血缘），不进合同 sha256。
        "public_interface": _public_interface,
        "public_interface_source": public_interface_identity(
            _public_interface, _public_interface_sha),
        # §10-5：输出合同（状态值/完整性/失败条件，全部取自 JSON）。
        "output_contract": {
            "status_values": output_contract["status_values"],
            "scored_entries": output_contract["scored_entries"],
            "action_score": output_contract["action_score"],
            "reason": output_contract["reason"],
            "batch_failure_conditions": output_contract["batch_failure_conditions"],
            "batch_failure_policy": output_contract["batch_failure_policy"],
        },
        # §10-4：结构化四字段。
        "mechanism_four_fields": dict(AV_MECHANISM_FIELD_NOTES),
        # §10-6：门线/位次势差口径（复审 §5 M4 的唯一来源；进合同身份）。
        "gate_line_semantics": gate_line_semantics_block(),
        # §10-6：作者守卫条款（未知取值 / 批次失败 / 修订行为差异；进合同身份）。
        "author_guard_semantics": author_guard_semantics_block(),
        # §10-6：研究数值口径；不要求模型自报「预计提分 N」。
        "numeric_reporting_rule": (
            "所有研究数值必须标明单位、根数、终点和不确定性；"
            "不要求也不接受自报「预计提分 N」"),
        "budget_note": budget_note,
        "identity_contract": {
            "candidate_id_inputs": identity.get("candidate_id_inputs", []),
            "candidate_id_excluded_provenance":
                identity.get("candidate_id_excluded_provenance", []),
            "note": "生成模型、提示词、算子、父代、调用账单作为出处另存，不进 candidate_id",
        },
        "compatibility": contract.get("compatibility", {}),
    }
    if parent is not None:
        payload["parent"] = {
            "identity": parent.get("identity"),
            "candidate_id": parent.get("candidate_id"),
            "thought": parent.get("thought"),
            "code": parent.get("code"),
            "code_sha256": parent.get("code_sha256"),
        }
    if feedback is not None:
        payload["feedback"] = {
            "facts": feedback.get("facts", ""),
            "associated_results": feedback.get("associated_results", ""),
            "mechanism_hypothesis": feedback.get("mechanism_hypothesis", ""),
            "note": "三段反馈（事实/关联结果/机制假设）只含开发结果；"
                    "不含确认集数据、未来牌墙真值",
        }
    return payload


def action_value_contract_identity(payload) -> str:
    """TaskContract 身份：规范化 JSON 的 sha256（进提示词对账）。"""

    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


#: 受限子集合规骨架：无 import、无注解、模块级只有 docstring 与函数定义；
#: 缺省实现返回 ABSTAIN（模板本身必须能通过静态子集检查）。
ACTION_VALUE_CODE_TEMPLATE = '''"""候选机制说明：<一句话>"""

def score_actions(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
    # <在这里实现你的机制：只允许任务合同里的受限子集与白名单>
    # 未知字段不得按已知 0 处理；无法评分时返回 ABSTAIN 并给出明确原因。
    return {"status": "ABSTAIN", "reason": "template: not implemented"}
'''


def render_action_value_contract_text(payload) -> str:
    """把 TaskContract 渲染成提示词文本（逐条可核对；数值全部来自 JSON）。"""

    lines = ["【任务合同（action_value_v1；机器合同 sha256={0}）】".format(
        str(payload.get("contract_sha256"))[:12])]
    lines += ["", "【本批目标与终端 U】",
              "  - " + str(payload["objective"]["summary"]),
              "  - 终端效用：" + str(payload["objective"]["terminal_utility"]),
              "  - " + str(payload["objective"]["note"])]
    lines += ["", "【工程面板边界】", "  - " + str(payload["panel_boundary"])]
    entry = payload["entry_point"]
    lines += ["", "【score_actions 完整签名（不得改动）】",
              "  - " + entry["signature"],
              "  - " + entry["docstring"],
              "  - hu_mode={0}：{1}".format(entry["hu_mode"], entry["hu_mode_note"]),
              "  - 排序合同：" + entry["rank_contract"]]
    view = payload["scoring_view"]
    lines += ["", "【ScoringView 字段（含义/单位/可空）schema={0}】".format(
        view["schema_version"])]
    for name, meaning in view["fields"].items():
        lines.append("  - {0}：{1}".format(name, meaning))
    # —— P10c：可用赛事基准（competition_bases）必须逐键进提示词 ——
    bases = view.get("competition_bases")
    lines.append("  - 可用积分基准（competition_bases；这些字段**存在且可判读**，"
                 "用上阶段账就看这里）：")
    if bases:
        masks = bases.get("freshness_masks") or {}
        lines.append("  - seat_order：" + str(bases.get("seat_order")))
        lines.append("  - units：" + str(bases.get("units")))
        lines.append("  - stage_scores：" + str(bases.get("stage_scores")))
        lines.append("  - table_scores：" + str(bases.get("table_scores")))
        lines.append("  - identity_mapping：" + str(bases.get("identity_mapping")))
        for index, item in enumerate(bases.get("admission_conditions") or (), start=1):
            lines.append("  - admission_conditions[{0}]：{1}".format(index, item))
        lines.append("  - unknown_is_not_zero：" + str(bases.get("unknown_is_not_zero")))
        lines.append("  - freshness_masks.order：" + "、".join(masks.get("order") or ()))
        lines.append("  - freshness_masks.values（闭集；不在表内不得臆造）："
                     + "、".join(masks.get("values") or ()))
        lines.append("  - staleness：" + str(bases.get("staleness")))
        lines.append("  - residual_risk：" + str(bases.get("residual_risk")))
        lines.append("  - current_stage_scores：" + str(bases.get("current_stage_scores")))
        for index, item in enumerate(bases.get("residual_gaps") or (), start=1):
            lines.append("  - residual_gaps[{0}]（未投影的可见事实，显式登记为剩余缺口）：{1}"
                         .format(index, item))
        # 合同新增键自动进提示词（未具名也要渲染，不得静默丢弃）。
        for key in sorted(bases):
            if key in AV_COMPETITION_NAMED_KEYS:
                continue
            lines.append("  - {0}（合同新增键，自动渲染）：{1}".format(key, bases[key]))
    else:
        lines.append("  - 合同未声明 competition_bases：不得臆造基准语义；"
                     "缺失即未知（不得补零、不得用另一基准顶替），"
                     "需用到阶段账时先确认渲染器与合同版本一致。")
    lines.append("  - 路线状态：{0}；进展：{1}".format(
        "/".join(view["route_states"]), "/".join(view["progress_states"])))
    lines.append("  - " + view["route_progress_note"])
    # —— C5：公开接口附录必须紧跟 ScoringView 概述（同一段输入合同语境）——
    lines += render_public_interface_lines("generation", payload.get("public_interface"))
    tools = payload["tool_catalog"]
    lines += ["", "【工具目录（冻结白名单；不在表内一律禁止）】",
              "  - 内建：" + "、".join(tools["builtins"]),
              "  - " + tools["builtin_notes"],
              "  - 只读方法：" + "、".join(tools["methods_readonly"]),
              "  - 运算符：" + "；".join(tools["operators"]),
              "  - import：" + ("全部禁止（" + tools["modules_note"] + "）"
                               if not tools["modules"] else "、".join(tools["modules"])),
              "  - 视图 API：" + tools["view_api"]]
    limits = payload["limits"]
    candidate_limits = limits["candidate"]
    lines += ["", "【数值与工作量限制（违反即拒绝装载）】"]
    for key in sorted(candidate_limits):
        lines.append("  - {0}：{1}".format(key, candidate_limits[key]))
    lines.append("  - 规则分析上限：" + json.dumps(
        limits["rule_analysis"], ensure_ascii=False))
    for rule in payload["metering_rules"]:
        lines.append("  - 计费：" + rule)
    lines.append("  - " + str(payload["limits_escalation"]))
    resp = payload["responsibility"]
    lines += ["", "【你的职责边界】",
              "  - " + resp["candidate_owns"]]
    for item in resp["candidate_must_not"]:
        lines.append("  - 禁止：" + item)
    for item in resp["subset_allowed"]:
        lines.append("  - 允许：" + item)
    # §10-6：静态规则清单紧跟在职责边界之后（同一段约束语境），逐条来自合同。
    lines += render_restricted_subset_rule_lines(payload.get("subset_rules"), "generation")
    oc = payload["output_contract"]
    lines += ["", "【输出合同】",
              "  - status 只能是 " + "/".join(oc["status_values"]),
              "  - " + oc["scored_entries"],
              "  - 条目字段：" + json.dumps(oc["action_score"], ensure_ascii=False),
              "  - reason：" + oc["reason"],
              "  - 整批失败条件：" + "；".join(oc["batch_failure_conditions"]),
              "  - 失败处置：" + oc["batch_failure_policy"]]
    lines += ["", "【结构化四字段（必须逐字段写清）】"]
    for name in AV_MECHANISM_FIELDS:
        lines.append("  - {0}：{1}".format(name, payload["mechanism_four_fields"][name]))
    gate = payload.get("gate_line_semantics") or {}
    if gate:
        lines += ["", "【门线/位次势差口径（唯一允许的定义；与目标合同 group_advance_v1 同源）】",
                  "  - 晋级区座位数=" + str(gate["advance_count"])
                  + str(gate["advance_count_source"]),
                  "  - 升序下标 ↔ 名次：" + "；".join(gate["order_statistic_mapping"])]
        for index, clause in enumerate(gate["clauses"], start=1):
            lines.append("  {0}) ".format(index) + clause)
        lines += ["  - 禁止的命名（名实必须一致）：" + "；".join(gate["forbidden_namings"]),
                  "  - 禁止的陈述（数学上不成立；引用即禁止，不得作为自己的解释）："
                  + "；".join(gate.get("forbidden_claims") or ()),
                  "  - 手算金例（值由同一参考实现算出；机制说明与反例必须与这些数字一致）："]
        for row in gate["golden_rows"]:
            lines.append(row)
        lines += ["  - 参考实现（受限子集内，可逐字复制成候选内的局部纯辅助函数；"
                  "下面这块只是公式原文，输出仍然只允许一个代码围栏）：",
                  FENCE + "python", str(gate["reference_implementation"]), FENCE]
    guard = payload.get("author_guard_semantics") or {}
    if guard:
        lines += ["", "【作者守卫条款（未知 / 批次失败 / 修订行为差异；唯一口径，必须自查）】"]
        for index, clause in enumerate(guard["clauses"], start=1):
            lines.append("  {0}) ".format(index) + clause)
        lines.append("  - 实测金例（值由同一参考实现算出；回复的机制说明必须与这些数字一致）：")
        for row in guard["golden_rows"]:
            lines.append(row)
        lines += ["  - 判定依据：" + str(guard["failure_source"]),
                  "  - 自查参考实现（受限子集内，可逐字复制成候选内的局部纯辅助函数；"
                  "下面这块只是公式原文，输出仍然只允许一个代码围栏）：",
                  FENCE + "python", str(guard["reference_implementation"]), FENCE]
    lines += ["", "【研究数值口径】", "  - " + payload["numeric_reporting_rule"]]
    if payload.get("budget_note"):
        lines += ["", "【预算说明】", "  - " + str(payload["budget_note"])]
    if payload.get("parent"):
        parent = payload["parent"]
        lines += ["", "【父代完整身份】", "  - candidate_id={0}；attempt={1}".format(
            str(parent.get("candidate_id"))[:16], parent.get("identity"))]
    if payload.get("feedback"):
        feedback = payload["feedback"]
        lines += ["", "【三段开发反馈（不含确认集数据）】",
                  "  1) 事实：" + str(feedback.get("facts") or "（无）"),
                  "  2) 关联结果：" + str(feedback.get("associated_results") or "（无）"),
                  "  3) 机制假设：" + str(feedback.get("mechanism_hypothesis") or "（无）")]
    lines += ["", "【角色】", "  - " + str(payload["prompt_role"])]
    return "\n".join(lines)


#: 新路径输出格式：机制一句话 + 结构化四字段 JSON + 唯一 python 围栏。
AV_OUTPUT_FORMAT_SECTION = """【输出格式（必须严格遵守，不得添加额外解释）】
1. 先用**一句话**说明你的新机制与主要步骤，这句话必须放在一个花括号 {{…}} 里面。
2. 然后给出结构化四字段说明，放在**唯一一个** {fence}json 围栏里，
   必须恰好包含 {fields} 四个键（每个键一段中文说明）。
3. 最后给出完整的 Python 代码，放在**唯一一个** {fence}python 围栏里，
   并且必须包含 score_actions(view) 的完整实现（函数名与签名逐字不得改动），
   不得 import 任何模块、不得定义 score_actions 之外的模块级可变状态：

{fence}python
{template}{fence}

不要输出解释、不要输出多个代码块、不要在代码块之外写代码。"""


def _av_output_format() -> str:
    return AV_OUTPUT_FORMAT_SECTION.format(
        fence=FENCE, fields="/".join(AV_MECHANISM_FIELDS),
        template=ACTION_VALUE_CODE_TEMPLATE.replace(FENCE, "@@@@@@"))


def build_action_value_prompt(operator: str, payload) -> PromptPacket:
    """I1/M1 提示词（新路径）。I1 不附伪造成绩；M1 附父代源码+身份+三段反馈。"""

    role = ("你是离线研发流程里的完整动作评分器设计者。你负责候选内部的动作取舍，"
            "不修改规则、接口、评估器或运行配置，不自行判定实验优胜或发布。")
    if operator == OPERATOR_M1:
        parent = payload.get("parent") or {}
        text = "\n".join([
            "请在给定父代的基础上修订完整动作评分器 score_actions，只输出一个机制与代码。",
            role, "",
            render_action_value_contract_text(payload), "",
            "【父代机制说明（逐字）】", str(parent.get("thought") or "（无）").strip(), "",
            "【父代代码（逐字）】", FENCE + "python",
            str(parent.get("code") or "").rstrip("\n"), FENCE, "",
            "修订要求：可以改条件分支、参数与尺度；不得改动函数合同、允许面与硬限制；",
            "必须在机制说明里写清「哪一条反馈导致哪一处改动」。", "",
            _av_output_format(),
        ])
    else:
        text = "\n".join([
            "请设计一个全新的完整动作评分器 score_actions。本通道不附带任何实验成绩：",
            "不存在「已知有效」的伪造成绩参考，也不要求你预测提分数值。",
            role, "",
            render_action_value_contract_text(payload), "",
            _av_output_format(),
        ])
    return PromptPacket(
        operator=operator, text=text,
        contract_identity=action_value_contract_identity(payload),
        parent_identity=(str((payload.get("parent") or {}).get("identity"))
                         if operator == OPERATOR_M1 else None),
        feedback_sha256=(sha256_text(json.dumps(payload.get("feedback") or {},
                                                 ensure_ascii=False, sort_keys=True))
                         if operator == OPERATOR_M1 else None))


#: 修复题的输出格式条款（与 r6/r9 任务表已签发的 T17—T20 逐字相同；此处只做
#: 单一来源化，不改一字：重签发时由本模块渲染，避免两套文案）。
AV_REPAIR_OUTPUT_FORMAT = (
    "【输出格式（必须严格遵守）】只输出**一个** {fence}python 围栏，内含修复后的完整"
    "候选源码（保留模块 docstring，函数名与签名不得改动）；围栏之前可以用几句话说明"
    "改了什么。不要输出多个代码块。"
)

#: 修复轮的输出形态**按判分器 kind 决定**，不按题面作者的口味：
#:   kind=code   → 判分器走 check_code（require_mechanism=True，mechanism 由 json 四字段围栏
#:                 解析而来）⇒ 修复轮与首答同一形态：一句话机制 + json 四字段 + 一个 python 围栏；
#:   kind=repair → 判分器走 check_repair（只看候选代码围栏）⇒ 维持「一个 python 围栏」。
#: P25 小诊断的装配缺陷：kind=code 的修复卡用了 kind=repair 的输出条款，模型照做就必然
#: MECHANISM_FIELDS_MISSING（规则对、题面错），因此这条必须由调用方把 kind 传进来。
AV_REPAIR_OUTPUT_KINDS: Tuple[str, ...] = ("code", "repair")

AV_REPAIR_OUTPUT_FORMAT_CODE = (
    "【输出格式（与判分器 kind=code 一致，必须严格遵守）】修复轮与首答同一交付形态：\n"
    "1. 先用**一句话**说明修复后的机制（改了什么），这句话放在一个花括号 {{…}} 里面。\n"
    "2. 再给结构化四字段说明，放在**唯一一个** {fence}json 围栏里，必须恰好包含 "
    "{fields} 四个键（每个键一段中文说明）——判分器按这四键判定机制说明是否齐全。\n"
    "3. 最后给出修复后的完整候选源码，放在**唯一一个** {fence}python 围栏里"
    "（保留模块 docstring，函数名与签名不得改动）。\n"
    "不要输出解释、不要输出多个代码块、不要在代码块之外写代码。"
)


def normalize_repair_output_kind(grader_kind) -> str:
    """判分器 kind → 修复卡输出形态（闭集；未知取值即 ValueError，不静默兜底）。"""

    kind = str(grader_kind or "repair").strip().lower()
    if kind not in AV_REPAIR_OUTPUT_KINDS:
        raise ValueError("未知的判分器 kind {0!r}（修复卡只支持 {1}）".format(
            grader_kind, "、".join(AV_REPAIR_OUTPUT_KINDS)))
    return kind


def repair_output_clause(grader_kind="repair") -> str:
    """修复卡的输出格式条款（按判分器 kind 取，两条都是唯一来源）。"""

    kind = normalize_repair_output_kind(grader_kind)
    if kind == "code":
        return AV_REPAIR_OUTPUT_FORMAT_CODE.format(
            fence=FENCE, fields="/".join(AV_MECHANISM_FIELDS))
    return AV_REPAIR_OUTPUT_FORMAT.format(fence=FENCE)


def render_action_value_repair_constraints(*, rules_path=None,
                                           target: str = "repair") -> str:
    """修复题面必须附带的受限子集静态规则块（与生成题同一份规则目录）。

    修复题（T17—T20）此前由 r6/r9 的任务表以**静态文本**签发，**不经过**
    render_action_value_contract_text：那一侧既没有【工具目录】白名单表，也没有
    本节规则块，而任务里又写着"不得改变函数合同与受限子集合规性"。P25 归因：
    三轮 18 次静态拒绝里有 6 次正落在修复题。本函数是修复题渲染的接入点。
    """

    rules, _digest = load_action_value_subset_rules(rules_path)
    return "\n".join(render_restricted_subset_rule_lines(rules, target))


def build_action_value_repair_prompt(materials_text: str, *,
                                     rules_path=None) -> PromptPacket:
    """修复题提示词：题面材料（逐字保留）+ 规则目录渲染的规则块 + 输出格式条款。

    材料文本由调用方提供（缺陷源码与合同条款引用属任务表内容，不进合同）；
    规则块**只从兄弟文件读**。operator 用 AV_OPERATOR_REPAIR；身份取
    「合同 sha256 + 规则目录 sha256」的组合（两者任一变化都改变提示词身份）。
    """

    contract, contract_digest = load_action_value_contract()
    rules, rules_digest = load_action_value_subset_rules(rules_path)
    appendix, appendix_digest = load_action_value_public_interface()
    text = "\n".join([
        str(materials_text).rstrip("\n"), "",
        "\n".join(render_restricted_subset_rule_lines(rules, "repair")), "",
        "\n".join(render_public_interface_lines("repair", appendix)).strip("\n"), "",
        AV_REPAIR_OUTPUT_FORMAT.format(fence=FENCE),
    ])
    return PromptPacket(
        operator=AV_OPERATOR_REPAIR, text=text,
        contract_identity=sha256_text(json.dumps(
            {"contract_sha256": contract_digest, "rules_sha256": rules_digest,
             "public_interface_sha256": appendix_digest},
            ensure_ascii=False, sort_keys=True)))


# ---------------------------------------------------------------------------
# 卡面瘦身（R9-P25 §4.3 / §3 第 2 步）：本次目标置顶 + 按机制相关性过滤
# ---------------------------------------------------------------------------
# 复审原话：「模型任务卡只保留**本次目标、完整父代、实际输入/输出合同、相关公开示例、
# 程序诊断和预算**。门线数学仅在相关任务提供对应片段；六十条规则可保留，但**不要用
# 长篇重复背景淹没本次修改点**。」
#
# 现状（改动前实测，T05）：43,325 字符里 16,683 是公开接口附录全文、6,993 是门线口径、
# 6,989 是作者守卫条款、3,451 是 60 条规则、4,278 是与附录重复的 ScoringView 概述——
# 而身份 4 准入的 b 轮失败里有 3 次是机械类静态违规（规则其实已公开）。本节把「本次
# 修改点」放到第一屏，其余按**逐题声明的机制相关性**过滤。
#
# 三条不可动摇的纪律：
#   1) **只删不加**：本节的渲染不新造任何字段名、数值或约束；被保留的文字逐字来自
#      contracts/*.json 或调用方给的父代/材料（同 render_public_interface_lines 的纪律）。
#   2) **fail-closed**：focus 缺键、含未知键、选了闭集外的字段组/模式，一律 ValueError；
#      附录里没有任何路径能落进静默黑洞——未选中的组必须在卡上显式列出。
#   3) **过滤不改判分**：判分器、门槛、合同字节、规则文件、附录文件都不动。本节只改
#      卡面文本，因此卡的 sha 变了（提示词身份），判分语义没变。

#: 卡面账目 schema（供验证脚本消费；字段稳定）。
AV_CARD_SCHEMA = "sitin-action-value-card/1"

#: 附录字段组闭集：group 名 → 路径前缀（按"段前缀"匹配，末尾 [] 在匹配时归一化；
#: 段数多者胜，段数相同则逐字等于路径的那个组胜出，故裸键 actions 与 actions[] 的元素
#: 不会互相吞并）。组的渲染顺序取自附录文件顺序（appendix_group_order），不取本表顺序。
#: 组的划分依据是**投影来源与语义归属**（visible_state = 可见牌局事实；actions[] = 待评分
#: 的动作表；competition = 赛事三份账；…），不是凭字数切的。
AV_CARD_FIELD_GROUPS: Tuple[Tuple[str, str], ...] = (
    ("actions[].followup_branches", "actions[].followup_branches"),
    ("actions[].routes[].conditional_settlement", "actions[].routes[].conditional_settlement"),
    ("actions[].routes[].conditions", "actions[].routes[].conditions"),
    ("actions[].routes[].useful_tiles", "actions[].routes[].useful_tiles"),
    ("actions[].routes", "actions[].routes"),
    ("actions[].immediate_settlement", "actions[].immediate_settlement"),
    ("actions[].family_progress_entries", "actions[].family_progress_entries"),
    ("actions[].value_issues", "actions[].value_issues"),
    ("actions[].useful_tiles", "actions[].useful_tiles"),
    ("actions[].standard_useful_tiles", "actions[].standard_useful_tiles"),
    ("actions[].seven_pairs_useful_tiles", "actions[].seven_pairs_useful_tiles"),
    ("actions[]", "actions[]"),
    ("actions", "actions"),
    ("visible_state.rule_state", "visible_state.rule_state"),
    ("visible_state", "visible_state"),
    ("competition", "competition"),
    ("analysis_profile", "analysis_profile"),
    ("reference_features", "reference_features"),
    ("schema_version", "schema_version"),
)
#: 落不进任何组的路径（附录将来新增字段时）统一进这个组，并且**恒被渲染**：
#: 过滤只能删掉「被显式归组且本题未选」的内容，绝不静默吞掉新字段。
AV_CARD_GROUP_FALLBACK = "未分组字段"
#: 无论 focus 怎么选都渲染的组（结构版本号是读任何字段的前提）。
AV_CARD_ALWAYS_GROUPS: Tuple[str, ...] = ("schema_version",)

#: focus 的合法取值（闭集；不在表内即 ValueError）。
AV_CARD_GATE_MODES: Tuple[str, ...] = ("full", "fragment", "none")
AV_CARD_GUARD_MODES: Tuple[str, ...] = ("full", "fragment", "none")
AV_CARD_EXAMPLE_MODES: Tuple[str, ...] = ("full", "output", "none")
AV_CARD_RULE_MODES: Tuple[str, ...] = ("compact", "full")
AV_CARD_OVERVIEW_MODES: Tuple[str, ...] = ("contract", "none")
#: focus 必填键与选填键（未知键即装配缺陷，fail-closed）。
AV_CARD_FOCUS_REQUIRED: Tuple[str, ...] = (
    "objective", "change_point", "input_groups",
)
AV_CARD_FOCUS_OPTIONAL: Tuple[str, ...] = (
    "schema", "gate", "guard", "guard_reference", "examples", "rules",
    "input_overview", "budget_note",
)

#: 判断「一句约束里是否出现了新的具体字面量」用的 token 口径：ASCII 标识符、数字串、
#: 以及 ASCII 标点与运算符（@、*、[]、** 等）。中文字符不算 token——规则文本里的中文
#: 多为解释性表述，而**执行器真正拒绝的字面量**几乎都是 ASCII。
AV_CARD_TOKEN_RE = re.compile("[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[!-/:-@\\[-\\x60{-~]")


def appendix_path_group(path: str) -> str:
    """附录路径 → 字段组（最长段前缀胜出；落不进任何组即 AV_CARD_GROUP_FALLBACK）。

    段前缀 = 把路径按 . 切开、去掉每段末尾的 [] 后逐段比较，因此
    actions[].followup_branches 能覆盖 actions[].followup_branches[].combined_shanten。
    """

    text = str(path)
    segments = [seg[:-2] if seg.endswith("[]") else seg for seg in text.split(".")]
    best = None
    best_score = (-1, -1)
    for name, prefix in AV_CARD_FIELD_GROUPS:
        want = [seg[:-2] if seg.endswith("[]") else seg for seg in prefix.split(".")]
        if segments[:len(want)] != want:
            continue
        # 段数多者胜；段数相同则**逐字等于路径**的那个组胜出（裸键 actions 与
        # actions[] 的元素在归一化后段数相同，只有字面比较能区分）。
        score = (len(want), 1 if text == prefix else 0)
        if score > best_score:
            best, best_score = name, score
    if best is None:
        return AV_CARD_GROUP_FALLBACK
    return best


def appendix_group_entries(appendix) -> Dict[str, List[Dict[str, Any]]]:
    """附录 → {字段组: [路径条目…]}（顺序保持附录文件顺序）。"""

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in appendix["paths"]:
        grouped.setdefault(appendix_path_group(entry["path"]), []).append(entry)
    return grouped


def appendix_group_order(appendix) -> List[str]:
    """按附录文件出现顺序排出字段组（渲染顺序 = 文件顺序，组间不乱序）。"""

    order: List[str] = []
    for entry in appendix["paths"]:
        group = appendix_path_group(entry["path"])
        if group not in order:
            order.append(group)
    return order


def normalize_card_focus(focus) -> Dict[str, Any]:
    """卡面 focus 声明 → 规范化（缺键/未知键/闭集外取值一律 ValueError）。"""

    if not isinstance(focus, Mapping):
        raise ValueError("卡面 focus 必须是对象")
    unknown = sorted(set(focus) - set(AV_CARD_FOCUS_REQUIRED) - set(AV_CARD_FOCUS_OPTIONAL))
    if unknown:
        raise ValueError("卡面 focus 含未知键（fail-closed，防拼写漂移）：{0}".format(
            "、".join(unknown)))
    missing = [key for key in AV_CARD_FOCUS_REQUIRED
               if not str(focus.get(key) or "").strip()]
    if missing:
        raise ValueError("卡面 focus 缺必填键：{0}".format("、".join(missing)))
    appendix, _digest = load_action_value_public_interface()
    known = set(appendix_group_order(appendix)) | {AV_CARD_GROUP_FALLBACK}
    groups = focus.get("input_groups")
    if not isinstance(groups, (list, tuple)) or not groups:
        raise ValueError("卡面 focus.input_groups 必须是非空列表")
    selected: List[str] = []
    for group in groups:
        name = str(group)
        if name not in known:
            raise ValueError("卡面 focus 声明了闭集外的字段组 {0!r}（闭集 {1}）".format(
                name, "、".join(sorted(known))))
        if name not in selected:
            selected.append(name)
    modes = {
        "gate": (focus.get("gate", "none"), AV_CARD_GATE_MODES),
        "guard": (focus.get("guard", "none"), AV_CARD_GUARD_MODES),
        "examples": (focus.get("examples", "output"), AV_CARD_EXAMPLE_MODES),
        "rules": (focus.get("rules", "compact"), AV_CARD_RULE_MODES),
        "input_overview": (focus.get("input_overview", "none"), AV_CARD_OVERVIEW_MODES),
    }
    normalized: Dict[str, Any] = {
        "schema": str(focus.get("schema") or AV_CARD_SCHEMA),
        "objective": str(focus["objective"]).strip(),
        "change_point": str(focus["change_point"]).strip(),
        "input_groups": selected,
        "budget_note": str(focus.get("budget_note") or "").strip(),
    }
    for name, (value, closed) in sorted(modes.items()):
        text = str(value)
        if text not in closed:
            raise ValueError("卡面 focus.{0}={1!r} 不在闭集 {2}".format(
                name, text, "、".join(closed)))
        normalized[name] = text
    normalized["guard_reference"] = bool(focus.get("guard_reference", False))
    return normalized


def card_focus_identity(focus) -> str:
    """规范化 focus 的身份（进提示词 contract_identity；改一个组即改身份）。"""

    return sha256_text(json.dumps(focus, ensure_ascii=False, sort_keys=True))


def compress_rule_statement(statement: str) -> Tuple[str, Tuple[str, ...]]:
    """规则 statement → 一条可执行约束（**只删不加**）。

    删法：把 statement 按「；」切成若干从句，保留首句；后续从句只有在**引入新的 ASCII
    字面量**（标识符/数字/运算符）时才保留——纯中文的复述与解释性从句被删掉。
    这样「违反即拒绝」的具体字面量（isinstance、**、@=、match、for…）一个不丢，
    去掉的是「超限拒绝装载。」「下划线前缀由执行器保留。」这类重复背景。
    返回 (压缩后文本, 被删从句元组)；被删从句逐条进卡面账目，可逐条复核。
    """

    text = str(statement).strip()
    segments = [seg.strip() for seg in text.split("；")]
    kept = [segments[0]]
    seen = set(AV_CARD_TOKEN_RE.findall(segments[0]))
    dropped: List[str] = []
    for segment in segments[1:]:
        if not segment:
            continue
        tokens = set(AV_CARD_TOKEN_RE.findall(segment))
        if tokens - seen:
            kept.append(segment)
            seen |= tokens
        else:
            dropped.append(segment)
    compressed = "；".join(kept)
    if not compressed.endswith("。"):
        # 补回的句号取自原文末尾（不是新造字符）：压缩结果始终是原文的**子序列**。
        tail = text[-1] if text and text[-1] in "。；：）" else "。"
        compressed += tail
    if len(compressed) > len(text):
        raise AssertionError("规则压缩不得加长文本：{0}".format(statement))
    return compressed, tuple(dropped)


def _card_section(name: str) -> List[str]:
    """统一的分节标题（首屏小节名固定，便于逐节量尺寸与机器对账）。"""

    return ["", "【{0}】".format(name)]


def render_card_goal_lines(payload, focus) -> List[str]:
    """【本次目标与修改点】——**第一屏**：本次做什么、改哪里、边界与预算。"""

    view = payload["objective"]
    lines = _card_section("本次目标与修改点（先读这一节）")
    lines.append("  - 本次目标：" + focus["objective"])
    lines.append("  - 本次修改点：" + focus["change_point"])
    lines.append("  - 角色：" + str(payload["prompt_role"]))
    lines.append("  - 本批目标：" + str(view["summary"]))
    lines.append("  - 终端 U：" + str(view["terminal_utility"]))
    lines.append("  - 工程面板边界：" + str(payload["panel_boundary"]))
    if focus["budget_note"]:
        lines.append("  - 预算：" + focus["budget_note"])
    lines.append("  - " + str(payload["numeric_reporting_rule"]))
    return lines


def render_card_parent_lines(payload) -> List[str]:
    """【父代完整材料】——身份 + 机制说明 + 完整源码（逐字，不截断）。"""

    parent = payload.get("parent") or {}
    lines = _card_section("父代完整材料（逐字；本次修改的起点）")
    lines.append("  - 完整身份：candidate_id={0}；code_sha256={1}".format(
        parent.get("candidate_id"), parent.get("code_sha256")))
    lines.append("  - 出处身份（逐字）：" + str(parent.get("identity")))
    lines.append("  - 父代机制说明（逐字）：")
    for line in str(parent.get("thought") or "（无）").strip().splitlines():
        lines.append("    " + line)
    lines.append("  - 父代读到的字段名以本节代码为准；输入合同只列本题机制相关的"
                 "字段组，未列出的按完整附录回查。")
    lines.append("  - 父代代码（逐字，完整）：")
    lines.append(FENCE + "python")
    lines.append(str(parent.get("code") or "").rstrip("\n"))
    lines.append(FENCE)
    return lines


def render_card_feedback_lines(payload) -> List[str]:
    """【三段开发反馈】——程序诊断（事实/关联结果/机制假设），逐字。"""

    feedback = payload.get("feedback") or {}
    lines = _card_section("三段开发反馈（程序诊断；不含确认集数据）")
    lines.append("  1) 事实：" + str(feedback.get("facts") or "（无）"))
    lines.append("  2) 关联结果：" + str(feedback.get("associated_results") or "（无）"))
    lines.append("  3) 机制假设：" + str(feedback.get("mechanism_hypothesis") or "（无）"))
    return lines


def render_card_input_contract(appendix, focus) -> Tuple[List[str], Dict[str, Any]]:
    """【输入合同（本题机制相关字段组）】+ 机器可读账目。

    路径行逐字来自附录（同 _appendix_path_line，不存在第二套文案）；
    未选中的字段组**显式列出**并给出完整附录指针——过滤不等于静默隐瞒。
    """

    grouped = appendix_group_entries(appendix)
    order = appendix_group_order(appendix)
    selected = [group for group in order
                if group in focus["input_groups"] or group in AV_CARD_ALWAYS_GROUPS]
    excluded = [group for group in order if group not in selected]
    lines = _card_section("输入合同（公开接口附录的本题相关字段组；schema={0}）".format(
        appendix.get("schema")))
    source = appendix.get("source_of_truth") or {}
    lines.append("  - 完整附录（全部 {0} 条路径 + 示例）：{1}；本卡只渲染下表列出的"
                 "字段组。".format(len(appendix["paths"]), AV_PUBLIC_INTERFACE_RELPATH))
    stats_excluded = []
    excluded_bits = []
    for group in excluded:
        entries = grouped.get(group) or []
        chars = sum(len(_appendix_path_line(entry)) + 1 for entry in entries)
        stats_excluded.append({"group": group, "entries": len(entries), "chars": chars})
        excluded_bits.append("{0}（{1} 条）".format(group, len(entries)))
    lines.append("  - 本题字段组（共 {0} 组）：{1}".format(len(selected), "、".join(selected)))
    lines.append("  - 本题未列出（机制不读；需要时按完整附录回查）："
                 + "、".join(excluded_bits) + "。")
    lines.append("  - 来源：{0} 的 {1}（schema={2}）；与 contracts/action-value-v1.json "
                 "分开存放，不进合同字节身份。".format(
                     source.get("projection_module"), source.get("projection_call"),
                     source.get("schema_version_value")))
    lines.append("  - 投影函数：{0}".format("、".join(source.get("projection_functions") or ())))
    for index, item in enumerate(appendix.get("conventions") or (), start=1):
        lines.append("  - 记法 {0}：{1}".format(index, item))
    rendered_paths = 0
    for group in selected:
        entries = grouped.get(group) or []
        rendered_paths += len(entries)
        # 组内 note 逐字相同的条目：note 只在组头出现一次（去重，不改一字）。
        notes = [entry.get("note") for entry in entries if entry.get("note")]
        shared = {note for note in notes if notes.count(note) > 1}
        lines.append("  - 字段组 {0}（{1} 条）：".format(group, len(entries)))
        for note in sorted(shared):
            lines.append("      * 本组公共 note（逐字，适用于组内多条路径）：" + str(note))
        for entry in entries:
            lines.append(_appendix_path_line(
                entry, skip_note=bool(entry.get("note")) and entry.get("note") in shared))
    lines.append("  - ScoringView 只读访问器实际形状：")
    for item in appendix["view_api"]:
        lines.append("  - {0} → {1}：{2}".format(item.get("name"), item.get("returns"),
                                                 item.get("note")))
    contract = appendix["output_contract"]
    lines.append("  - 输出：status 只能是 " + "/".join(contract.get("status_values") or ()))
    lines.append("  - SCORED：" + str(contract.get("scored")))
    lines.append("  - ABSTAIN：" + str(contract.get("abstain")))
    forms = contract.get("reason_three_forms") or []
    lines.append("  - reason 的三种合法形态：" + "；".join(str(item) for item in forms))
    lines.append("  - reason 空字符串：" + str(contract.get("reason_empty_string_rejected")))
    lines.append("  - 未知 ≠ 0：" + str(contract.get("unknown_is_not_zero")))
    lines.append("  - 整批失败：" + str(contract.get("batch_failure")))
    group_keys = set(selected)
    selected_paths = [entry["path"] for group in selected
                      for entry in (grouped.get(group) or [])]
    lines += render_card_example_lines(appendix, focus, group_keys, selected_paths)
    stats = {
        "appendix_total_paths": len(appendix["paths"]),
        "rendered_paths": rendered_paths,
        "selected_groups": selected,
        "excluded_groups": stats_excluded,
    }
    return lines, stats


def render_card_example_lines(appendix, focus, group_keys=None,
                              selected_paths=None) -> List[str]:
    """公开示例：按本题字段组截取（**值逐字未改**），模式由 focus.examples 决定。

    full   = 最小合法输入 + 三种输出范例（C5 要求的"一个合法输入与两种输出"）
    output = 只保留输出范例（修复题只需要输出形态）
    none   = 不给示例，只给指针
    """

    mode = focus["examples"]
    if mode == "none":
        return ["  - 公开示例：本题不给示例正文；需要时读完整附录 {0} 的 examples 段。"
                .format(AV_PUBLIC_INTERFACE_RELPATH)]
    examples = appendix.get("examples") or {}
    lines: List[str] = []
    if mode == "full" and examples.get("input") is not None:
        trimmed = _card_trim_example(examples["input"], group_keys, selected_paths)
        lines.append("  - 最小合法输入（真实投影的 candidate_view；按本题字段组截取，"
                     "被截去的顶层键不属于本题字段组）：")
        for line in json.dumps(trimmed, ensure_ascii=False, sort_keys=True,
                               indent=1).splitlines():
            lines.append("    " + line)
    outputs = examples.get("outputs") or []
    if outputs:
        lines.append("  - 合法/不合法输出范例（前两条合法；第三条必须整批失败）：")
        for index, item in enumerate(outputs, start=1):
            lines.append("    {0}) {1}".format(index, item.get("label")))
            lines.append("       " + json.dumps(item.get("value"), ensure_ascii=False,
                                                sort_keys=True))
    return lines


def _card_trim_example(value, group_keys, selected_paths=None):
    """示例输入按字段组截取顶层键（值不动；未选字段组整枝剪掉）。

    顶层键 K 保留的条件：K 自己的组被选中，**或**有被选中的路径落在 K 之下
    （例如选了 visible_state.rule_state 就得保留 visible_state 这一枝，
    否则卡上列了路径、示例里却没有容器，读者会以为容器不存在）。
    """

    if group_keys is None or not isinstance(value, Mapping):
        return value
    paths = tuple(selected_paths or ())
    trimmed = {}
    for key, item in value.items():
        name = str(key)
        if appendix_path_group(name) in group_keys:
            trimmed[key] = item
            continue
        if any(path == name or path.startswith(name + ".") for path in paths):
            trimmed[key] = item
    return trimmed


def render_card_rule_lines(rules, target: str, mode: str = "compact"):
    """【受限子集静态规则】——编号全保留；compact 模式只删解释性从句。

    返回 (行列表, 账目)。账目逐条记下被删从句，供"删了什么"清单逐条复核。
    """

    if mode not in AV_CARD_RULE_MODES:
        raise ValueError("未知规则渲染模式 {0!r}（闭集 {1}）".format(mode, AV_CARD_RULE_MODES))
    selected = subset_rules_for_target(rules, target)
    if not selected:
        return ["", "【受限子集静态规则（AV-SUB）】",
                "  - 合同未声明适用于 {0} 的 restricted_subset.rules 条目：本提示词"
                "缺少静态规则清单，属装配缺陷（fail-closed，不得读成「没有约束」）。"
                .format(target)], {"rules": 0, "before_chars": 0, "after_chars": 0,
                                   "dropped_clauses": []}
    before = sum(len(rule["statement"]) for rule in selected)
    lines = ["", "【受限子集静态规则（AV-SUB；{0} 条全部保留；违反即拒绝装载）】"
                 .format(len(selected)),
             "  - 与执行器静态检查同源；预检失败给出命中的编号，按编号回查本节；"
             "这里逐条只删了不引入新字面量的解释从句，原文见 {0}。"
             .format(AV_SUBSET_RULES_RELPATH)]
    dropped: List[Dict[str, str]] = []
    after = 0
    for rule in selected:
        if mode == "full":
            text = rule["statement"]
            clauses: Tuple[str, ...] = ()
        else:
            text, clauses = compress_rule_statement(rule["statement"])
        after += len(text)
        for clause in clauses:
            dropped.append({"id": rule["id"], "clause": clause})
        lines.append("  - {0}：{1}".format(rule["id"], text))
    return lines, {"rules": len(selected), "before_chars": before, "after_chars": after,
                   "dropped_clauses": dropped}


def render_card_output_contract_lines(payload) -> List[str]:
    """【输出合同】——判分器直接消费的字段（status/entries/score/reason/失败条件）。"""

    oc = payload["output_contract"]
    lines = _card_section("输出合同（判分器逐条核对）")
    lines.append("  - status 只能是 " + "/".join(oc["status_values"]))
    lines.append("  - " + oc["scored_entries"])
    lines.append("  - 条目字段：" + json.dumps(oc["action_score"], ensure_ascii=False))
    lines.append("  - reason：" + oc["reason"])
    lines.append("  - 整批失败条件：" + "；".join(oc["batch_failure_conditions"]))
    lines.append("  - 失败处置：" + oc["batch_failure_policy"])
    lines += _card_section("结构化四字段（必须逐字段写清）")
    for name in AV_MECHANISM_FIELDS:
        lines.append("  - {0}：{1}".format(name, payload["mechanism_four_fields"][name]))
    return lines


def render_card_gate_lines(payload, focus) -> Tuple[List[str], Dict[str, Any]]:
    """门线/位次势差口径：full / fragment / none（**不相关任务不给**）。

    fragment = 定义与条款（本题机制要用的那一层），去掉金例与参考实现；
    none     = 一行指针，说明本题机制不涉及门线数学。
    """

    mode = focus["gate"]
    gate = payload.get("gate_line_semantics") or {}
    if not gate or mode == "none":
        return (["", "【门线/位次势差口径】", "  - 本题机制不涉及门线/位次势差计算；"
                 "完整口径见 contracts/action-value-v1.json（引用请按合同原文，"
                 "不要自造名次说法）。"], {"gate_mode": "none"})
    lines = _card_section("门线/位次势差口径（唯一允许的定义；与目标合同 group_advance_v1 同源）")
    lines.append("  - 晋级区座位数=" + str(gate["advance_count"])
                 + str(gate["advance_count_source"]))
    lines.append("  - 升序下标 ↔ 名次：" + "；".join(gate["order_statistic_mapping"]))
    for index, clause in enumerate(gate["clauses"], start=1):
        lines.append("  {0}) ".format(index) + clause)
    lines.append("  - 禁止的命名（名实必须一致）：" + "；".join(gate["forbidden_namings"]))
    lines.append("  - 禁止的陈述（数学上不成立；引用即禁止，不得作为自己的解释）："
                 + "；".join(gate.get("forbidden_claims") or ()))
    if mode == "full":
        lines.append("  - 手算金例（值由同一参考实现算出；机制说明与反例必须与这些数字一致）：")
        for row in gate["golden_rows"]:
            lines.append(row)
        lines += ["  - 参考实现（受限子集内，可逐字复制成候选内的局部纯辅助函数；"
                  "下面这块只是公式原文，输出仍然只允许一个代码围栏）：",
                  FENCE + "python", str(gate["reference_implementation"]), FENCE]
    else:
        lines.append("  - 手算金例与参考实现见 contracts/action-value-v1.json 的"
                     "门线口径段（本题不需要逐位复核，故不展开）。")
    return lines, {"gate_mode": mode}


def render_card_guard_lines(payload, focus) -> Tuple[List[str], Dict[str, Any]]:
    """作者守卫条款：full / fragment / none（条款 + 实测金例；参考实现按开关）。"""

    mode = focus["guard"]
    guard = payload.get("author_guard_semantics") or {}
    if not guard or mode == "none":
        return (["", "【作者守卫条款】", "  - 本题机制不涉及未知越位的运行期判定；"
                 "完整条款见 contracts/action-value-v1.json 的 output_contract。"
                 "（未知≠0 的硬约束仍在下文【输出合同】与本卡输入合同的字段可空条件里。）"],
                {"guard_mode": "none"})
    lines = _card_section("作者守卫条款（未知 / 批次失败 / 修订行为差异；唯一口径，必须自查）")
    for index, clause in enumerate(guard["clauses"], start=1):
        lines.append("  {0}) ".format(index) + clause)
    lines.append("  - 实测金例（值由同一参考实现算出；回复的机制说明必须与这些数字一致）：")
    for row in guard["golden_rows"]:
        lines.append(row)
    lines.append("  - 判定依据：" + str(guard["failure_source"]))
    if mode == "full" or focus["guard_reference"]:
        lines += ["  - 自查参考实现（受限子集内，可逐字复制成候选内的局部纯辅助函数；"
                  "下面这块只是公式原文，输出仍然只允许一个代码围栏）：",
                  FENCE + "python", str(guard["reference_implementation"]), FENCE]
    else:
        lines.append("  - 自查参考实现（未知下限/已知最低分的取法）见 contracts/"
                     "action-value-v1.json 的守卫条款段；本题不给可复制实现，"
                     "请按上面的条款与金例自查。")
    return lines, {"guard_mode": mode, "guard_reference": bool(focus["guard_reference"])}


def render_card_limits_lines(payload) -> List[str]:
    """【数值与工作量限制】+ 计费 + 升级口径（判分器会在装载期执行）。"""

    limits = payload["limits"]
    lines = _card_section("数值与工作量限制（违反即拒绝装载）")
    for key in sorted(limits["candidate"]):
        lines.append("  - {0}：{1}".format(key, limits["candidate"][key]))
    lines.append("  - 规则分析上限：" + json.dumps(limits["rule_analysis"], ensure_ascii=False))
    for rule in payload["metering_rules"]:
        lines.append("  - 计费：" + rule)
    lines.append("  - " + str(payload["limits_escalation"]))
    resp = payload["responsibility"]
    lines.append("  - " + resp["candidate_owns"])
    for item in resp["candidate_must_not"]:
        lines.append("  - 禁止：" + item)
    for item in resp["subset_allowed"]:
        lines.append("  - 允许：" + item)
    return lines


def render_card_tool_catalog_lines(payload) -> List[str]:
    """【工具目录】——冻结白名单（静态检查执行的就是这张表）。"""

    tools = payload["tool_catalog"]
    lines = _card_section("工具目录（冻结白名单；不在表内一律禁止）")
    lines.append("  - 内建：" + "、".join(tools["builtins"]))
    lines.append("  - " + tools["builtin_notes"])
    lines.append("  - 只读方法：" + "、".join(tools["methods_readonly"]))
    lines.append("  - 运算符：" + "；".join(tools["operators"]))
    lines.append("  - import：" + ("全部禁止（" + tools["modules_note"] + "）"
                                   if not tools["modules"] else "、".join(tools["modules"])))
    lines.append("  - 视图 API：" + tools["view_api"])
    return lines


def render_card_entry_lines(payload) -> List[str]:
    """【score_actions 完整签名】——判分器按此签名装载，逐字不得改。"""

    entry = payload["entry_point"]
    lines = _card_section("score_actions 完整签名（不得改动）")
    lines.append("  - " + entry["signature"])
    lines.append("  - " + entry["docstring"])
    lines.append("  - hu_mode={0}：{1}".format(entry["hu_mode"], entry["hu_mode_note"]))
    lines.append("  - 排序合同：" + entry["rank_contract"])
    return lines


def render_card_budget_lines(payload, focus) -> List[str]:
    """【预算说明】——预算/限额段保留（复审清单里的"预算"）。"""

    note = focus["budget_note"] or str(payload.get("budget_note") or "")
    if not note:
        note = "预算以最新授权与台账为准；失败与重试同样计费。"
    return _card_section("预算说明") + ["  - " + note]


def render_card_overview_lines(payload, focus) -> List[str]:
    """CompetitionContext 三份账的语义块（合同 scoring_view.competition_bases）。

    这是**合同**里的口径（不在附录里），只有 input_overview=contract 的题才展开；
    其余题给一行指针，避免把 2 KB 的账本语义塞进不读赛事账的机制。
    """

    view = payload["scoring_view"]
    if focus["input_overview"] != "contract":
        lines: List[str] = []
        route_groups = {"actions[].routes", "actions[].routes[].conditions",
                        "actions[].routes[].conditional_settlement",
                        "actions[].routes[].useful_tiles",
                        "actions[].family_progress_entries"}
        if route_groups & set(focus["input_groups"]):
            # 机制要读路线/家族进展 ⇒ 这两个闭集枚举与口径必须在卡上（附录不重复它们）。
            lines.append("  - 路线状态：{0}；进展：{1}".format(
                "/".join(view["route_states"]), "/".join(view["progress_states"])))
            lines.append("  - " + view["route_progress_note"])
        lines.append("  - 赛事上下文（competition）三份账的命名/相加/未知口径见合同段 "
                     "scoring_view.competition_bases（本题机制不读赛事账，故不展开；"
                     "需要时按合同原文回查）。")
        return lines
    lines = ["  - 路线状态：{0}；进展：{1}".format(
        "/".join(view["route_states"]), "/".join(view["progress_states"])),
        "  - " + view["route_progress_note"]]
    bases = view.get("competition_bases")
    lines.append("  - 赛事上下文（competition）字段：" + str(view["fields"].get("competition")))
    lines.append("  - 可用积分基准（competition_bases；这些字段存在且可判读，"
                 "用上阶段账就看这里）：")
    if not bases:
        lines.append("  - 合同未声明 competition_bases：不得臆造基准语义；缺失即未知"
                     "（不得补零、不得用另一基准顶替）。")
        return lines
    masks = bases.get("freshness_masks") or {}
    for key in sorted(bases):
        if key in ("freshness_masks", "residual_gaps", "admission_conditions"):
            continue
        lines.append("  - {0}：{1}".format(key, bases[key]))
    for index, item in enumerate(bases.get("admission_conditions") or (), start=1):
        lines.append("  - admission_conditions[{0}]：{1}".format(index, item))
    lines.append("  - freshness_masks.order：" + "、".join(masks.get("order") or ()))
    lines.append("  - freshness_masks.values（闭集；不在表内不得臆造）："
                 + "、".join(masks.get("values") or ()))
    for index, item in enumerate(bases.get("residual_gaps") or (), start=1):
        lines.append("  - residual_gaps[{0}]（未投影的可见事实，显式登记为剩余缺口）：{1}"
                     .format(index, item))
    return lines


def render_action_value_card_text(payload, focus) -> str:
    """瘦身后的任务卡（生成题/M1 修订题）。

    顺序 = 复审要求的优先级：**本次目标与修改点 → 完整父代 → 程序诊断 → 本次机制相关
    的输入合同 → 静态规则 → 输出合同 → 门线/守卫片段（仅相关任务）→ 限额与预算 →
    输出格式**。渲染只做「取合同/附录的原文字段 + 分节 + 按组过滤」，不新造约束。
    """

    focus = normalize_card_focus(focus)
    appendix, appendix_digest = load_action_value_public_interface()
    rules, rules_digest = load_action_value_subset_rules()
    lines: List[str] = []
    lines += render_card_goal_lines(payload, focus)
    if payload.get("parent"):
        lines += render_card_parent_lines(payload)
    if payload.get("feedback"):
        lines += render_card_feedback_lines(payload)
    lines += render_card_entry_lines(payload)
    contract_lines, _appendix_stats = render_card_input_contract(appendix, focus)
    lines += contract_lines
    lines += render_card_overview_lines(payload, focus)
    lines += render_card_tool_catalog_lines(payload)
    rule_lines, _rule_stats = render_card_rule_lines(rules, "generation", focus["rules"])
    lines += rule_lines
    lines += render_card_output_contract_lines(payload)
    gate_lines, _gate_stats = render_card_gate_lines(payload, focus)
    lines += gate_lines
    guard_lines, _guard_stats = render_card_guard_lines(payload, focus)
    lines += guard_lines
    lines += render_card_limits_lines(payload)
    lines += render_card_budget_lines(payload, focus)
    lines.append("")
    lines.append("（本卡按本次机制相关性过滤；附录 sha256={0}，规则目录 sha256={1}）"
                 .format(appendix_digest[:12], rules_digest[:12]))
    return "\n".join(lines)


def card_render_report(payload, focus) -> Dict[str, Any]:
    """卡面机器可读账目：逐节尺寸、字段组进出、规则压缩明细。

    验证脚本消费本账目，实现"删了什么、为什么可以删"的逐条对账；不写文件、不改状态。
    """

    focus = normalize_card_focus(focus)
    appendix, appendix_digest = load_action_value_public_interface()
    rules, rules_digest = load_action_value_subset_rules()
    _contract_lines, appendix_stats = render_card_input_contract(appendix, focus)
    _rule_lines, rule_stats = render_card_rule_lines(rules, "generation", focus["rules"])
    card = render_action_value_card_text(payload, focus)
    legacy = render_action_value_contract_text(payload)
    if payload.get("parent"):
        legacy += "\n" + "\n".join([
            "", "【父代机制说明（逐字）】",
            str(payload["parent"].get("thought") or "").strip(),
            "", "【父代代码（逐字）】", FENCE + "python",
            str(payload["parent"].get("code") or "").rstrip("\n"), FENCE])
    if payload.get("feedback"):
        feedback = payload["feedback"]
        legacy += "\n" + "\n".join([
            "", "【三段开发反馈（不含确认集数据）】",
            "  1) 事实：" + str(feedback.get("facts") or "（无）"),
            "  2) 关联结果：" + str(feedback.get("associated_results") or "（无）"),
            "  3) 机制假设：" + str(feedback.get("mechanism_hypothesis") or "（无）")])
    sections: List[Dict[str, Any]] = []
    current = "(前言)"
    for line in card.split("\n"):
        match = re.match(r"^【(.+?)】$", line)
        if match:
            current = match.group(1)
            sections.append({"name": current, "chars": 0})
        elif sections:
            sections[-1]["chars"] += len(line) + 1
        else:
            sections.append({"name": current, "chars": len(line) + 1})
    return {
        "schema": AV_CARD_SCHEMA,
        "focus": focus,
        "focus_identity": card_focus_identity(focus),
        "appendix_sha256": appendix_digest,
        "rules_sha256": rules_digest,
        "legacy_chars": len(legacy),
        "card_chars": len(card),
        "sections": sections,
        "appendix": appendix_stats,
        "rules": rule_stats,
    }


def build_action_value_card_prompt(operator: str, payload, focus) -> PromptPacket:
    """瘦身卡的 PromptPacket（operator 与旧路径同语义，身份含 focus）。

    contract_identity = 旧合同身份 + focus 身份 + 附录 sha：改一个字段组即改身份，
    因此"换了卡"与"换了合同"在血缘上不会混成同一次调用。
    """

    focus = normalize_card_focus(focus)
    contract, digest = load_action_value_contract()
    _rules, rules_digest = load_action_value_subset_rules()
    _appendix, appendix_digest = load_action_value_public_interface()
    role = ("你是离线研发流程里的完整动作评分器设计者。你负责候选内部的动作取舍，"
            "不修改规则、接口、评估器或运行配置，不自行判定实验优胜或发布。")
    if operator == OPERATOR_M1:
        head = ["请在给定父代的基础上修订完整动作评分器 score_actions，"
                "只输出一个机制与代码。",
                role, "",
                "修订要求：可以改条件分支、参数与尺度；不得改动函数合同、允许面与硬限制；",
                "必须在机制说明里写清「哪一条反馈导致哪一处改动」。",
                "（父代材料、三段反馈与本次修改点都在本卡第一屏之后的小节里。）"]
    else:
        head = ["请设计一个全新的完整动作评分器 score_actions。本通道不附带任何实验成绩：",
                "不存在「已知有效」的伪造成绩参考，也不要求你预测提分数值。",
                role]
    text = "\n".join(head + [render_action_value_card_text(payload, focus), "",
                              _av_output_format()])
    parent = payload.get("parent") or {}
    return PromptPacket(
        operator=operator, text=text,
        contract_identity=sha256_text(json.dumps(
            {"contract_sha256": digest, "rules_sha256": rules_digest,
             "public_interface_sha256": appendix_digest,
             "card_focus": card_focus_identity(focus)},
            ensure_ascii=False, sort_keys=True)),
        parent_identity=(str(parent.get("identity")) if operator == OPERATOR_M1 else None),
        feedback_sha256=(sha256_text(json.dumps(payload.get("feedback") or {},
                                                ensure_ascii=False, sort_keys=True))
                         if operator == OPERATOR_M1 else None))


def render_action_value_repair_card_text(materials_text: str, focus,
                                         rules_path=None,
                                         grader_kind="repair") -> str:
    """瘦身后的修复题卡：**本次目标与修改点置顶** + 材料逐字 + 相关输入合同 + 规则。

    材料（缺陷源码、合同条款、缺陷定位提示、任务）逐字保留——它是"完整父代/实际输入"，
    只是不再让 16 KB 的附录全文挡在它前面。

    grader_kind 决定输出条款（见 repair_output_clause）：kind=code 的题由 check_code 判分，
    require_mechanism=True ⇒ 修复轮必须交「一句话 + json 四字段 + 一个 python 围栏」，
    并因此附上四字段写法说明；kind=repair 的题维持「一个 python 围栏」，逐字节不变。
    """

    output_kind = normalize_repair_output_kind(grader_kind)
    focus = normalize_card_focus(focus)
    contract, _digest = load_action_value_contract()
    rules, rules_digest = load_action_value_subset_rules(rules_path)
    appendix, appendix_digest = load_action_value_public_interface()
    lines = _card_section("本次目标与修改点（先读这一节）")
    lines.append("  - 本次目标：" + focus["objective"])
    lines.append("  - 本次修改点：" + focus["change_point"])
    if focus["budget_note"]:
        lines.append("  - 预算：" + focus["budget_note"])
    lines.append("  - 材料在下一节逐字给出（缺陷源码 + 合同条款 + 缺陷定位 + 任务）。")
    contract_lines, _stats = render_card_input_contract(appendix, focus)
    lines += contract_lines
    rule_lines, _rule_stats = render_card_rule_lines(rules, "repair", focus["rules"])
    lines += rule_lines
    oc = contract["output_contract"]
    lines += _card_section("输出合同（判分器逐条核对）")
    lines.append("  - status 只能是 " + "/".join(oc["status_values"]))
    lines.append("  - " + oc["scored_entries"])
    lines.append("  - 条目字段：" + json.dumps(oc["action_score"], ensure_ascii=False))
    lines.append("  - reason：" + oc["reason"])
    lines.append("  - 整批失败条件：" + "；".join(oc["batch_failure_conditions"]))
    lines.append("  - 失败处置：" + oc["batch_failure_policy"])
    if output_kind == "code":
        # 判分器按 json 四字段围栏判 require_mechanism ⇒ 修复卡必须给出四字段写法要求。
        lines += _card_section("结构化四字段（修复说明必须逐字段写清）")
        for name in AV_MECHANISM_FIELDS:
            lines.append("  - {0}：{1}".format(name, AV_MECHANISM_FIELD_NOTES[name]))
    lines += render_card_budget_lines({}, focus)
    head = "\n".join(lines)
    text = "\n".join([head, "", str(materials_text).rstrip("\n"), "",
                       repair_output_clause(output_kind), "",
                       "（本卡按本次机制相关性过滤；附录 sha256={0}，规则目录 sha256={1}）"
                       .format(appendix_digest[:12], rules_digest[:12])])
    return text


def build_action_value_repair_card_prompt(materials_text: str, focus,
                                          rules_path=None,
                                          grader_kind="repair") -> PromptPacket:
    """瘦身修复卡的 PromptPacket（材料逐字进卡；身份含 focus、kind 与两份兄弟文件 sha）。"""

    output_kind = normalize_repair_output_kind(grader_kind)
    focus = normalize_card_focus(focus)
    _contract, contract_digest = load_action_value_contract()
    _rules, rules_digest = load_action_value_subset_rules(rules_path)
    _appendix, appendix_digest = load_action_value_public_interface()
    text = render_action_value_repair_card_text(materials_text, focus, rules_path,
                                                grader_kind=output_kind)
    if str(materials_text).rstrip("\n") not in text:
        raise AssertionError("修复题渲染改写了材料正文（只允许前置本次目标并追加约束）")
    return PromptPacket(
        operator=AV_OPERATOR_REPAIR, text=text,
        contract_identity=sha256_text(json.dumps(
            {"contract_sha256": contract_digest, "rules_sha256": rules_digest,
             "public_interface_sha256": appendix_digest,
             "card_focus": card_focus_identity(focus),
             "repair_output_kind": output_kind},
            ensure_ascii=False, sort_keys=True)))


def parse_action_value_reply(raw: str) -> Dict[str, Any]:
    """解析新路径回复：{一句话} + json 四字段围栏 + python 代码围栏。

    思想/代码复用 parse_model_reply（entry 名换成 score_actions）；四字段
    JSON 缺失或键不全时状态为 missing_mechanism——机制说明不完整的候选
    不得进入装载（§10 结构化四字段是合同必含项）。
    """

    parsed = parse_model_reply(raw, entry_name=AV_ENTRY_NAME,
                               require_entry_definition=True)
    mechanism = None
    problems = list(parsed.problems)
    text = (raw or "").replace("\r\n", "\n")
    json_spans = [match for match in _FENCE_RE.finditer(text)
                  if match.group(0).lstrip().startswith(FENCE + "json")]
    if json_spans:
        try:
            data = json.loads(json_spans[0].group(1).strip())
            missing = [name for name in AV_MECHANISM_FIELDS
                       if not str(data.get(name) or "").strip()]
            if missing:
                problems.append("四字段缺项：" + "、".join(missing))
            else:
                mechanism = {name: str(data[name]) for name in AV_MECHANISM_FIELDS}
        except ValueError as exc:
            problems.append("四字段 JSON 不可解析：{0}".format(exc))
    else:
        problems.append("未找到 json 围栏的四字段说明块")
    status = parsed.status
    if status == PARSE_OK and mechanism is None:
        status = PARSE_MISSING_MECHANISM
    return {
        "status": status,
        "thought": parsed.thought,
        "mechanism": mechanism,
        "code": parsed.code,
        "problems": problems,
    }


def precheck_action_value_candidate(code_text: str) -> Dict[str, Any]:
    """生成端/修复端预检：候选源码先过 action_value_executor 静态子集检查。

    不通过即生成失败（照常消耗本次调用额度，§9.3 失败也消耗额度）；与
    门禁/执行器共用同一 static_check 实现（单一来源，不复制）。

    失败信息**照原样保留**（problems 第一条仍是执行器原话，不删不改写），
    另外按合同 restricted_subset.rules[].message_pattern 把消息绑回稳定编号：
    rule_ids 给出命中编号、rule_hits 给出编号加候选可读约束。命中不到编号时
    rule_ids 为空并置 unmapped=True——**不猜**，也不放宽任何判据。
    """

    from hangma_bot.policy.action_value_executor import static_check
    try:
        static_check(code_text)
    except ValueError as exc:
        message = str(exc)
        hits = subset_rule_hits(message)
        return {"ok": False, "problems": [message],
                "rule_ids": [hit["id"] for hit in hits],
                "rule_hits": hits,
                "unmapped": not hits}
    except KeyError as exc:
        # 执行器缺陷（AV-SUB-A01）：嵌套函数引用顶层函数名时 _check_recursion
        # 抛 KeyError 而不是 StaticCheckError。仍未通过装载 ⇒ 照旧判失败，
        # 只是把"工具崩溃"如实记成"预检失败 + 执行器缺陷"，不让异常穿透预检
        # （异常穿透会把候选失败误记成工具故障，并丢掉诊断）。
        message = ("执行器静态检查异常（非 StaticCheckError，见 AV-SUB-A01）："
                   "{0}: {1}".format(type(exc).__name__, exc))
        return {"ok": False, "problems": [message], "rule_ids": [], "rule_hits": [],
                "unmapped": True, "executor_defect": "KeyError"}
    return {"ok": True, "problems": [], "rule_ids": [], "rule_hits": [],
            "unmapped": False}


def _av_llm_fail_closed(args: Any, backend_kind: str) -> Optional[str]:
    """零预算红线：无授权时对真实 LLM 调用 fail-closed（不读私有凭据文件）。

    replay/delegate（文件式）/dry-run/emit 不发真实请求，允许离线运行；
    api/headless 是真实调用，缺 --llm-authorization 授权文件时直接拒绝，
    且**不触碰** .private/sitin-llm.json（连读都不读）。
    """

    offline = (args.dry_run or args.emit_prompt or args.ingest_reply
               or backend_kind in (BACKEND_REPLAY, BACKEND_DELEGATE))
    if offline:
        return None
    if getattr(args, "llm_authorization", None):
        data = json.loads(Path(args.llm_authorization).read_text(encoding="utf-8"))
        if data.get("authorized") is True:
            return None
        return "授权文件未置 authorized=true：拒绝真实 LLM 调用"
    return ("无 LLM 调用授权：action_value_v1 生成路径对真实调用 fail-closed"
            "（可用 --replay 离线夹具或 --backend delegate 文件式交接；"
            "不读取 .private/sitin-llm.json）")


class _AvContractShim:
    """emit_prompt 按旧 delta 合同形状消费四个键；这里把 action-value 机器
    合同映射到同一形状（不复制数值，全部取自渲染载荷与合同 JSON 原文）：

    - facts ← scoring_view + whitelist（tool_catalog）+ predicates_binding；
    - limits ← limits（含规则分析与候选限额）；
    - counterexamples ← output_contract.batch_failure_conditions（整批失败
      条件即"什么时候不该生效"的机器反例表）；
    - forbidden ← restricted_subset.forbidden（合同 JSON 原文）。

    emit_prompt 的旧 delta 语义与 delegation-request.json 的 how_to_use
    协议不改；多余键（schema/contract_sha256）不进四个消费点，仅供对账。
    """

    def __init__(self, payload) -> None:
        self._payload = dict(payload)

    def to_json(self) -> Dict[str, Any]:
        raw, _digest = load_action_value_contract()
        return {
            "facts": {
                "scoring_view": dict(self._payload.get("scoring_view") or {}),
                "whitelist": dict(self._payload.get("tool_catalog") or {}),
                "predicates_binding": dict(raw.get("predicates_binding") or {}),
                "entry_point": dict(self._payload.get("entry_point") or {}),
            },
            "limits": dict(self._payload.get("limits") or {}),
            "counterexamples": list(
                (self._payload.get("output_contract") or {})
                .get("batch_failure_conditions") or []),
            "forbidden": list(
                (raw.get("restricted_subset") or {}).get("forbidden") or []),
            "schema": self._payload.get("schema"),
            "contract_sha256": self._payload.get("contract_sha256"),
        }


class _AvAttemptContext:
    """delegate 交接用的最小 AttemptContext 等价物（复用 emit_prompt）。"""

    def __init__(self, operator: str, packet: PromptPacket, payload) -> None:
        self.operator = operator
        self.packet = packet
        self.contract = _AvContractShim(payload)


def av_parent_binding(parent_dir: Path) -> Dict[str, Any]:
    """核验 **action_value_v1** 父代产物（schema sitin-action-value-generation/1）。

    与 legacy parent_binding 同一条纪律：**按持久化产物重算**，不信命令行。
    拒绝条件（同款 ValueError）：记录 schema 不符、目录缺 candidate.py、
    代码哈希与 parsed.json.code_sha256 不一致、父代解析未通过
    （record.parse.status 与 parsed.json.status 都必须是 ok，篡改任一即拒）。
    **装载失败的候选仍可作父代**（修复路径入口）；装载状态如实带入不遮掩。
    返回与 legacy parent_binding 同形状 dict；identity 用 record.identity.
    candidate_id 与 prompt.sha256 组合（血缘可逐项对账）。
    """

    parent_dir = Path(parent_dir)
    record_path = parent_dir / "record.json"
    if not record_path.is_file():
        raise ValueError("父代目录缺少 record.json：{0}".format(parent_dir))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != AV_GENERATION_SCHEMA:
        raise ValueError("父代记录 schema 不符：{0!r}（action_value_v1 需要 {1}）".format(
            record.get("schema"), AV_GENERATION_SCHEMA))
    code_path = parent_dir / "candidate.py"
    if not code_path.is_file():
        raise ValueError("父代目录缺少 candidate.py：{0}".format(parent_dir))
    actual = sha256_file(code_path)
    parsed_path = parent_dir / "parsed.json"
    parsed = {}
    if parsed_path.is_file():
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    recorded_code_sha = parsed.get("code_sha256") or (
        (record.get("parse") or {}).get("code_sha256"))
    if actual != recorded_code_sha:
        raise ValueError("父代代码与记录不一致：实际 {0}，记录 {1}".format(
            short(actual), short(recorded_code_sha)))
    parse_status = (record.get("parse") or {}).get("status")
    parsed_status = parsed.get("status")
    if parse_status != PARSE_OK or (parsed_status is not None
                                    and parsed_status != PARSE_OK):
        raise ValueError("父代解析未通过（record {0!r}/parsed {1!r}，"
                         "没有可用的 thought/code），不能作为修订基础".format(
                             parse_status, parsed_status))
    identity_block = record.get("identity") or {}
    candidate_id = identity_block.get("candidate_id")
    prompt_sha = (record.get("prompt") or {}).get("sha256") or ""
    if not candidate_id:
        raise ValueError("父代记录缺 identity.candidate_id：{0}".format(parent_dir))
    return {
        "dir": str(parent_dir),
        "identity": "{0}:{1}".format(candidate_id, prompt_sha),
        "candidate_id": candidate_id,
        "prompt_sha256": prompt_sha,
        "code_sha256": actual,
        "record_sha256": sha256_file(record_path),
        "operator": record.get("operator"),
        "thought": (record.get("parse") or {}).get("thought") or "",
        "code": code_path.read_text(encoding="utf-8"),
        "load_ok": bool((record.get("load") or {}).get("ok")),
        "precheck_ok": bool((record.get("precheck") or {}).get("ok")),
        "repair_depth": int((record.get("lineage") or {}).get("repair_depth", 0)),
        "verified": True,
    }


def _run_generate_action_value(args: Any, operator: str) -> int:
    """新路径生成 runner：合同渲染 → 提示词 → 回复 → 预检 → 受监管装载 → 血缘。"""

    out_dir = guard_out_dir(Path(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)
    writes = WriteLedger(out_dir)
    backend_kind = BACKEND_REPLAY if args.replay else args.backend

    refused = _av_llm_fail_closed(args, backend_kind)
    if refused is not None:
        print(json.dumps({"ok": False, "refused": refused}, ensure_ascii=False))
        return 3

    parent = None
    if operator == OPERATOR_M1:
        if not args.parent:
            raise ValueError("M1 必须有父代；请给 --parent <父代目录>")
        # 新产物结构走 av_parent_binding（schema sitin-action-value-generation/1）；
        # legacy parent_binding 只服务旧 delta 记录，互不重解释。
        bound = av_parent_binding(Path(args.parent))
        parent = {
            "identity": bound["identity"],
            "candidate_id": bound["candidate_id"],
            "prompt_sha256": bound["prompt_sha256"],
            "attempt_dir": bound["dir"],
            "code_sha256": bound["code_sha256"],
            "thought": bound.get("thought") or "",
            "code": bound["code"],
            "load_ok": bound.get("load_ok"),
        }
    feedback_payload = None
    if operator == OPERATOR_M1:
        raw_feedback = _load_feedback(args)
        feedback_payload = {"facts": raw_feedback, "associated_results": "",
                            "mechanism_hypothesis": ""}
        if args.three_segment_feedback:
            feedback_payload = json.loads(
                Path(args.three_segment_feedback).read_text(encoding="utf-8"))

    payload = render_action_value_task_contract(
        objective_summary=(args.objective or default_objective_summary()),
        panel_boundary=(args.panel_boundary or
                        "开发面板：条件机会面板 + 正常阶段面板（group-dev-v1，2 桌）"),
        prompt_role=("M1 修订：在父代与三段反馈基础上做有界改动"
                     if operator == OPERATOR_M1 else
                     "I1 初始化：全新完整评分器；不附伪造成绩"),
        parent=parent, feedback=feedback_payload,
        budget_note=(args.budget_note or "预算以最新授权与台账为准；失败与重试同样计费"))
    packet = build_action_value_prompt(operator, payload)

    if args.dry_run:
        print(packet.text)
        print("\n--- prompt_sha256: {0}".format(packet.sha256), file=sys.stderr)
        return 0

    gates = _load_sibling("sitin_gates")
    ledger = GenerationBudget.load(out_dir / "budget.json",
                                   calls_budget=args.calls_budget, writes=writes,
                                   max_total_tokens=args.max_total_tokens)
    ledger.check_token_budget()
    entry = ledger.reserve("{0}-av/{1}".format(operator, backend_kind))
    try:
        if args.ingest_reply or args.replay:
            reply_file = Path(args.ingest_reply or args.replay)
            data = load_reply_envelope(reply_file, prompt_sha256=packet.sha256)
            reply = ModelReply(
                text=data["reply"], backend=args.backend, origin=data["origin"],
                provider=data.get("provider"), model=data.get("model"),
                captured_at_utc=data.get("captured_at_utc"),
                usage=data.get("usage") or {}, finish_reason=data.get("finish_reason"),
                note=data.get("note"), delegator=data.get("delegator"))
        elif backend_kind == BACKEND_DELEGATE:
            context = _AvAttemptContext(operator, packet, payload)
            info = emit_prompt(context, out_dir, backend=backend_kind, writes=writes,
                               parent_dir=Path(args.parent) if args.parent else None)
            info["contract_identity"] = packet.contract_identity
            print(json.dumps(info, ensure_ascii=False, indent=2))
            ledger.settle(entry, "completed", note="delegate emit only")
            return 0
        else:
            raise TransportError(
                "action_value_v1 路径只支持 replay/delegate（离线）或显式授权的真实通道；"
                "已按零预算红线 fail-closed")
        ledger.charge_tokens(reply.usage)

        attempt_dir = out_dir / ("attempts/" + operator + "-" + packet.sha256[:12])
        attempt_dir.mkdir(parents=True, exist_ok=True)
        writes.write_text(attempt_dir / "prompt.txt", packet.text)
        writes.write_text(attempt_dir / "reply_raw.txt", reply.text)
        parsed = parse_action_value_reply(reply.text)
        code_text = normalized_code(parsed["code"]) if parsed["code"] else None
        writes.write_json(attempt_dir / "parsed.json", {
            "status": parsed["status"], "thought": parsed["thought"],
            "mechanism": parsed["mechanism"],
            "code_sha256": sha256_text(code_text) if code_text else None,
            "problems": parsed["problems"]})

        precheck = {"ok": False, "problems": ["解析未通过，未做预检"]}
        load_json = {"ok": False, "reason": "解析未通过，未进入装载"}
        identity = None
        if parsed["status"] == PARSE_OK and code_text:
            writes.write_text(attempt_dir / "candidate.py", code_text)
            precheck = precheck_action_value_candidate(code_text)
            if precheck["ok"]:
                load_json = gates.load_candidate_supervised(code_text, "sample")
                identity = gates.av_identity_binding(code_text)
            else:
                load_json = {"ok": False,
                             "reason": "静态预检未通过：" + ";".join(precheck["problems"]),
                             "supervised": False}
        record = {
            "schema": AV_GENERATION_SCHEMA,
            "operator": operator,
            "backend": backend_kind,
            "created_at_utc": utc_now(),
            "contract": {"identity": packet.contract_identity,
                         "payload": payload,
                         "contract_sha256": payload["contract_sha256"]},
            "prompt": {**packet.to_json(), "path": "prompt.txt"},
            "reply": {"path": "reply_raw.txt",
                      "raw_sha256": sha256_text(reply.text),
                      "provider": reply.provider, "model": reply.model,
                      "usage": reply.usage,
                      "evidence_kind": reply.evidence_kind},
            "parse": parsed,
            "precheck": precheck,
            "load": {"ok": bool(load_json.get("ok")),
                     "reason": load_json.get("message") or load_json.get("reason"),
                     "supervised": bool(load_json.get("supervised"))},
            "identity": identity,
            "parent": parent,
            "budget": {"spent_calls": ledger.spent_calls,
                       "remaining_calls": ledger.remaining,
                       "call_tokens": usage_tokens(reply.usage)},
            "admission_eligible": False,
            "note": "生成记录不等于准入；门禁走 sitin_gates.admit_action_value 独立记录",
        }
        writes.write_json(attempt_dir / "record.json", record)
        writes.append_text(out_dir / "records.jsonl",
                           json.dumps({"schema": AV_GENERATION_SCHEMA,
                                       "operator": operator,
                                       "parse_status": parsed["status"],
                                       "precheck_ok": precheck["ok"],
                                       "load_ok": record["load"]["ok"],
                                       "prompt_sha256": packet.sha256,
                                       "created_at_utc": record["created_at_utc"],
                                       "attempt_dir": str(attempt_dir.relative_to(out_dir))},
                                      ensure_ascii=False) + "\n")
        ledger.settle(entry, "completed",
                      attempt_identity=packet.sha256[:24],
                      parse_status=parsed["status"],
                      load_ok=record["load"]["ok"])
        print(json.dumps({
            "parse_status": parsed["status"],
            "precheck_ok": precheck["ok"],
            "load_ok": record["load"]["ok"],
            "candidate_id": (identity or {}).get("candidate_id"),
            "attempt_dir": str(attempt_dir.relative_to(out_dir)),
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:                              # noqa: BLE001 —— 失败也要记账
        ledger.settle(entry, "failed", error="{0}: {1}".format(type(exc).__name__, exc))
        raise

# ============================================================ 2. 提示词

@dataclass(frozen=True)
class PromptPacket:
    """一次生成的提示词与其身份。

    `sha256` 是**提示词原文**的哈希：落盘实录里的 `prompt_sha256`
    必须与它逐字节相符，否则拒绝摄入（防止"拿另一次回复冒充这一次"）。
    """

    operator: str
    text: str
    contract_identity: str
    parent_identity: Optional[str] = None
    feedback_sha256: Optional[str] = None

    @property
    def sha256(self) -> str:
        return sha256_text(self.text)

    def to_json(self) -> Dict[str, Any]:
        return {
            "operator": self.operator,
            "sha256": self.sha256,
            "chars": len(self.text),
            "contract_identity": self.contract_identity,
            "parent_identity": self.parent_identity,
            "feedback_sha256": self.feedback_sha256,
        }


#: 反引号（chr(96)）。源码里用 FENCE 常量拼接，避免连续三个反引号造成阅读歧义。
FENCE = chr(96) * 3


#: EoH 的统一输出格式（本地化）；出处见模块 docstring §1。
OUTPUT_FORMAT_SECTION = """【输出格式（必须严格遵守，不得添加额外解释）】
1. 先用**一句话**说明你的新机制与主要步骤，这句话必须放在一个花括号 {{…}} 里面。
2. 然后给出完整的 Python 代码，放在**唯一一个** {fence}python 围栏里，
   并且必须包含下面这个函数的完整实现（函数名与签名逐字不得改动）：

{fence}python
{template}{fence}

不要输出解释、不要输出多个代码块、不要在代码块之外写代码。"""


def _output_format() -> str:
    """渲染输出格式段；模板里的围栏先用占位替换，避免嵌套围栏解析错位。"""

    return OUTPUT_FORMAT_SECTION.format(
        fence=FENCE, template=CODE_TEMPLATE.replace(FENCE, "@@@@@@"))


def build_i1_prompt(contract: TaskContract) -> PromptPacket:
    """I1：初始化提示词（任务 + 允许信息 + 函数合同 + 单位 + 限制 + 反例）。"""

    text = "\n".join([
        "你是离线研发流程里的候选机制设计者。你只设计**一个**评分调整机制并写出代码，",
        "不评价好坏、不决定取舍、不做实验结论。",
        "",
        contract.render(),
        "",
        _output_format(),
    ])
    return PromptPacket(operator=OPERATOR_I1, text=text,
                        contract_identity=contract.identity())


def build_m1_prompt(contract: TaskContract, parent_thought: str, parent_code: str,
                    feedback: str, *, parent_identity: str) -> PromptPacket:
    """M1：修订提示词（在父代基础上做**有界**改动）。

    父代代码与说明逐字进提示词；父代身份单独记录，便于"提示词里的父代"与
    "血缘里绑定的父代"对账。反馈允许包含开发集表现与拒绝诊断，
    **不得**包含独立确认集信息（DESIGN §3.4 边界）。
    """

    fence = FENCE
    text = "\n".join([
        "你是离线研发流程里的候选机制设计者。请**在给定父代的基础上修订**一个评分调整机制，",
        "只输出一个机制与它的代码；不评价好坏、不决定取舍、不做实验结论。",
        "",
        contract.render(),
        "",
        "【父代身份】",
        parent_identity,
        "",
        "【父代机制说明（逐字）】",
        parent_thought.strip(),
        "",
        "【父代代码（逐字）】",
        fence + "python",
        parent_code.rstrip("\n"),
        fence,
        "",
        "【反馈（来自开发集或拒绝诊断；不含独立确认集信息）】",
        feedback.strip() or "（无）",
        "",
        "修订要求：可以改条件分支、门控、参数与尺度；**不得**改动函数合同、允许面与硬限制；",
        "必须在说明里写清「哪一条反馈导致哪一处改动」。",
        "",
        _output_format(),
    ])
    return PromptPacket(operator=OPERATOR_M1, text=text,
                        contract_identity=contract.identity(),
                        parent_identity=parent_identity,
                        feedback_sha256=sha256_text(feedback))


# ============================================================ 3. 模型调用后端（可插拔）

#: 后端种类。**四种后端落盘的血缘 schema 完全一致**，换通道不改变证据形状。
BACKEND_DELEGATE = "delegate"     # 文件式交接：本工具只产出提示词 / 摄入回复，不自己调用模型
BACKEND_REPLAY = "replay"         # 回放已落盘的原始回复（逐字节可复现）
BACKEND_API = "api"               # OpenAI 兼容 HTTP；凭据只从私有配置/环境读
BACKEND_HEADLESS = "headless"     # **本轮未实现**：需要 dsh headless profile，是否启用由用户决定
BACKENDS = (BACKEND_DELEGATE, BACKEND_REPLAY, BACKEND_API, BACKEND_HEADLESS)

#: 落盘回复的来源；**由文件自己声明，且必须与后端一致**。
ORIGIN_DELEGATED = "delegated_model_reply"
ORIGIN_CAPTURED = "model_capture"
ORIGIN_FIXTURE = "format_fixture"
#: headless 的回复由工具**自己**从子进程 stdout 取得（没有落盘封套），因此单列一个来源。
ORIGIN_HEADLESS = "headless_capture"
#: 有"落盘封套"要校验的三种来源；headless 不在其中。
ORIGINS = (ORIGIN_DELEGATED, ORIGIN_CAPTURED, ORIGIN_FIXTURE)

#: 来源 → 记录里的 `evidence_kind`（机器可核验，不由调用方口头声明）。
ORIGIN_EVIDENCE_KIND = {
    ORIGIN_HEADLESS: REPLY_HEADLESS,
    ORIGIN_DELEGATED: REPLY_DELEGATED,
    ORIGIN_CAPTURED: REPLY_CAPTURED,
    ORIGIN_FIXTURE: REPLY_FIXTURE,
}

#: **GL-9**：来源的**取证强度**。委派/回落封套由人填写（`--origin/--provider/--model`），
#: **没有签名、没有回执**，因此只能算"自述"，不能声称"机器可核验"；
#: api/headless 是工具自己发出请求/读到 stdout 与运行痕迹，属"工具观测"。
PROVENANCE_ATTESTATION: Dict[str, str] = {
    ORIGIN_DELEGATED: "envelope-self-declared",
    ORIGIN_CAPTURED: "envelope-self-declared",
    ORIGIN_FIXTURE: "human-authored-fixture",
    ORIGIN_HEADLESS: "tool-observed-stdout-and-session-log",
}

#: 各来源必须齐备的字段；缺一即拒绝摄入（fail-closed）。
_ORIGIN_REQUIRED: Dict[str, Tuple[str, ...]] = {
    ORIGIN_DELEGATED: ("provider", "model", "captured_at_utc", "delegator"),
    ORIGIN_CAPTURED: ("provider", "model", "captured_at_utc"),
    ORIGIN_FIXTURE: ("author", "purpose"),
}

#: 默认凭据环境变量名。**凭据只从环境或私有配置读**，绝不写进任何产物。
DEFAULT_API_KEY_ENV = "SITIN_LLM_API_KEY"
#: 指向"同格式凭据文件"的环境变量（优先级高于默认路径）。
CONFIG_ENV = "SITIN_LLM_CONFIG"
#: 只给密钥的环境变量（其余取默认端点）。
KEY_ONLY_ENV = "DEEPSEEK_API_KEY"
#: 私有凭据文件默认路径（本仓 .gitignore 内；不得入库、不得复制进任何产物）。
DEFAULT_CONFIG_PATH = _project_file(_PROJECT_ROOT, '.private/sitin-llm.json')
#: 仅给密钥时的默认端点（与私有配置里的 base_url 一致）。
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_CHAT_PATH = "/chat/completions"
#: api 后端的**默认档位**：用户裁定本轮参考跑用 `deepseek-flash`（配置里的 junior 档）。
#: 该端点另有 `deepseek-v4-pro`（senior 档）可选，本轮不使用；显式 `--tier senior` 仍可用。
DEFAULT_TIER = "junior"
DEFAULT_REQUEST_TIMEOUT_SEC = 120.0
#: headless 通道：每次调用起一个 DSH 子进程，时延明显高于直连 HTTP，故上限给宽。
HEADLESS_PROFILE = "headless"
#: headless 默认 DSH_HOME（**仓库内、已在 .gitignore**；密钥只走环境变量，绝不写进这里）。
DEFAULT_DSH_HOME = _project_file(_PROJECT_ROOT, REPO / ".dsh-headless")
DEFAULT_HEADLESS_TIMEOUT_SEC = 1800.0
#: headless 通道的提示词后缀：**信息边界的补偿措施**，不是等价物。
#: 该通道本质是一个具备工作区能力的 agent，只能靠提示词约束"不要用工具、不要读文件"，
#: 因此每条记录都标 info_boundary="weak"，不假装它和 api 直连一样干净。
HEADLESS_PROMPT_SUFFIX = (
    "\n\n【本通道的硬约束】只回答，不要使用任何工具，不要读取或写入任何文件，"
    "不要访问网络，不要执行命令。直接按上面的输出格式给出回复。"
)
#: **实测调高**：该端点（deepseek-flash）4K/16K 预算会被思维链吃满、正文为空；
#: 合法区间是 [1, 393216]（Lead 实测），因此默认留足余量到 131072。
DEFAULT_MAX_TOKENS = 131072
DEFAULT_TEMPERATURE = 0.6
DEFAULT_TOP_P = 0.95


class TransportError(RuntimeError):
    """模型调用失败；**绝不返回伪造回复**，由调用方记为失败并保留状态。"""


class ReplyEnvelopeError(ValueError):
    """落盘回复文件不合法（缺字段、来源与后端不符、提示词哈希不符）。"""


@dataclass(frozen=True)
class ModelReply:
    """一次模型往返的结果；**原始文本逐字保留**。"""

    text: str
    backend: str
    origin: str
    provider: Optional[str]
    model: Optional[str]
    captured_at_utc: Optional[str]
    usage: Mapping[str, Any]
    http_status: Optional[int] = None
    finish_reason: Optional[str] = None
    note: Optional[str] = None
    delegator: Optional[str] = None
    #: 端点是哪台主机（**只记主机名**，不记路径与查询串，更不记凭据）。
    endpoint_host: Optional[str] = None
    #: 请求时声明的模型 id（响应里的 model 可能带版本后缀，两个都要能对账）。
    model_requested: Optional[str] = None
    #: 推理型模型会另给 `reasoning_content`：**只记存在与否和长度，绝不当回复内容**
    #: （第三阶段 Lead 实测踩到：max_tokens 太小只有思维链、正文为空）。
    reasoning_present: Optional[bool] = None
    reasoning_chars: Optional[int] = None
    #: headless 通道：从会话痕迹里读到的**实际**模型配置（provider/model/reasoningEffort）。
    observed_config: Optional[Mapping[str, Any]] = None
    #: headless 通道：本次运行写出的会话文件路径（身份的可追溯出处）。
    session_file: Optional[str] = None
    #: headless 通道的调用耗时（每次都要起一个 DSH 进程，比直连 HTTP 慢得多）。
    elapsed_sec: Optional[float] = None
    #: 信息边界强度：api 直连是 "strong"（没有工具与文件能力）；
    #: headless 是 "weak"（运行体具备工作区能力，只能靠提示词约束）。
    info_boundary: Optional[str] = None
    #: 用量从哪来：@@BT@@response_body@@BT@@（HTTP 响应自带）或 @@BT@@session_log@@BT@@（会话痕迹累加）。
    usage_source: Optional[str] = None

    @property
    def evidence_kind(self) -> str:
        return ORIGIN_EVIDENCE_KIND[self.origin]

    @property
    def provenance_attestation(self) -> str:
        """取证强度（GL-9）：封套自述只是"谁填的谁负责"，不等于"工具观测到的"。

        - `tool-observed-http`：api 直连——请求与响应都是工具自己发出/收到的；
        - `tool-observed-stdout-and-session-log`：headless——stdout 与运行痕迹都是工具读到的；
        - `envelope-self-declared`：delegate/replay 封套由人填写，**没有签名也没有回执**；
        - `human-authored-fixture`：人工夹具，本来就不是模型输出。
        """

        if self.backend == BACKEND_API:
            return "tool-observed-http"
        return PROVENANCE_ATTESTATION.get(self.origin, "unknown")

    def to_json(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "origin": self.origin,
            "evidence_kind": self.evidence_kind,
            # GL-9：来源是"自述"还是"工具观测到的"，逐条写清楚
            "provenance_attestation": self.provenance_attestation,
            "is_model_output": self.origin != ORIGIN_FIXTURE,
            "provider": self.provider,
            "model": self.model,
            "captured_at_utc": self.captured_at_utc,
            "delegator": self.delegator,
            "http_status": self.http_status,
            "finish_reason": self.finish_reason,
            "usage": dict(self.usage),
            "chars": len(self.text),
            "note": self.note,
            "endpoint_host": self.endpoint_host,
            "model_requested": self.model_requested,
            "reasoning_present": self.reasoning_present,
            "reasoning_chars": self.reasoning_chars,
            "observed_config": dict(self.observed_config) if self.observed_config else None,
            "session_file": self.session_file,
            "elapsed_sec": self.elapsed_sec,
            "info_boundary": self.info_boundary,
            "usage_available": bool(self.usage),
            "usage_source": self.usage_source,
        }


def usage_tokens(usage: Optional[Mapping[str, Any]]) -> int:
    """取本次调用的 token 总数（取不到就记 0，**不猜**）。

    两种命名都要认（Lead 实测更正）：
      - HTTP 响应：`total_tokens` / `prompt_tokens` / `completion_tokens`（snake_case）；
      - DSH 会话日志：`totalTokens` / `inputTokens` / `outputTokens`（camelCase）。
    headless 通道的用量只有后者——拿不到就等于"花多少看不见"，预算账本因此没法用。
    """

    if not usage:
        return 0

    def _int(*keys: str) -> Optional[int]:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    total = _int("total_tokens", "totalTokens")
    if total is not None:
        return total
    parts = [value for value in (_int("prompt_tokens", "inputTokens"),
                                 _int("completion_tokens", "outputTokens"))
             if value is not None]
    return sum(parts)


#: 采样参数：**进记录、进提示词哈希之外的请求身份**。None 表示"未显式设置"。
@dataclass(frozen=True)
class SamplingSpec:
    temperature: Optional[float] = DEFAULT_TEMPERATURE
    top_p: Optional[float] = DEFAULT_TOP_P
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    seed: Optional[int] = None

    def to_json(self) -> Dict[str, Any]:
        return {"temperature": self.temperature, "top_p": self.top_p,
                "max_tokens": self.max_tokens, "seed": self.seed}

    def to_request_fields(self) -> Dict[str, Any]:
        """**实际进入请求体**的字段（None 表示未显式设置，请求体里就不带它）。"""

        return {key: value for key, value in self.to_json().items() if value is not None}

    def omitted_fields(self) -> List[str]:
        """未显式设置、因此没有进入请求体的字段名。"""

        return sorted(key for key, value in self.to_json().items() if value is None)


def _config_file_secrets() -> List[str]:
    """从私有凭据文件里取出密钥明文——**只用于遮蔽与泄漏检查，绝不写进产物**。

    为什么必须包括它：真实调用时密钥来自私有文件而不是环境变量，
    只扫描环境变量会让"落盘内容里有没有密钥"这道复核形同虚设。
    """

    candidates: List[Path] = []
    if os.environ.get(CONFIG_ENV):
        candidates.append(Path(os.environ[CONFIG_ENV]))
    candidates.append(DEFAULT_CONFIG_PATH)
    found: List[str] = []
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                 # noqa: BLE001 —— 读不到就跳过
            continue
        if not isinstance(data, dict):
            continue
        profiles = data.get("endpoints")
        profiles = profiles if isinstance(profiles, dict) else {"_": data}
        for profile in profiles.values():
            if isinstance(profile, dict) and profile.get("api_key"):
                found.append(str(profile["api_key"]))
    return found


def collect_secrets(explicit: Optional[str] = None) -> Tuple[str, ...]:
    """收集需要**主动遮蔽**的凭据明文（只用于遮蔽检查，绝不落盘）。"""

    secrets: List[str] = []
    if explicit:
        secrets.append(explicit)
    for name in (DEFAULT_API_KEY_ENV, KEY_ONLY_ENV, "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        value = os.environ.get(name)
        if value:
            secrets.append(value)
    secrets.extend(_config_file_secrets())
    return tuple(dict.fromkeys(secrets))


def redact(text: str, secrets: Sequence[str]) -> str:
    """把凭据明文替换成占位符；长度小于 8 的值不替换（避免误伤正常文本）。"""

    result = text
    for secret in secrets:
        if secret and len(secret) >= 8:
            result = result.replace(secret, "[REDACTED]")
    return result


def find_leaked_secrets(payload: Any, secrets: Sequence[str]) -> List[str]:
    """扫描将要落盘的内容里是否含凭据明文；**发现即拒绝写出**。"""

    blob = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
    return [short(sha256_text(s), 8) for s in secrets if s and len(s) >= 8 and s in blob]


def resolve_api_credentials(config_path: Optional[Path] = None, *,
                            endpoint: Optional[str] = None,
                            model: Optional[str] = None,
                            tier: Optional[str] = None,
                            api_key_env: str = DEFAULT_API_KEY_ENV) -> Dict[str, Any]:
    """按**固定顺序**解析调用凭据与端点（第三阶段 Lead 指定的顺序）。

    1. 显式 `--config`（最高优先，便于换文件不改环境）
    2. 环境变量 `SITIN_LLM_CONFIG`（指向同格式文件）
    3. 环境变量 `DEEPSEEK_API_KEY`（**只给密钥**，端点与路径取默认值）
    4. 默认私有路径 `.private/sitin-llm.json`

    支持的两种文件形状：
      - `schema=sitin-llm-credentials/1`：`endpoints.<名>.{base_url,chat_path,api_key,models}`，
        端点名取 `--endpoint` 或文件里的 `default_endpoint`；
      - 扁平形状：`{base_url, chat_path, api_key, models, provider}`。

    **凭据绝不进入返回值以外的任何地方**：返回的 `api_key` 只被传输层用来拼
    `Authorization` 头，任何产物、日志与异常文本都只出现"来源"与长度指纹。
    """

    source = ""
    data: Dict[str, Any] = {}
    chosen_path: Optional[Path] = None
    if config_path is not None:
        chosen_path, source = Path(config_path), "cli --config"
    elif os.environ.get(CONFIG_ENV):
        chosen_path, source = Path(os.environ[CONFIG_ENV]), "env {0}".format(CONFIG_ENV)
    elif os.environ.get(KEY_ONLY_ENV):
        return {
            "base_url": DEFAULT_BASE_URL, "chat_path": DEFAULT_CHAT_PATH,
            "api_key": os.environ[KEY_ONLY_ENV], "provider": "deepseek",
            "models": {}, "model": model, "tier": tier or DEFAULT_TIER,
            "source": "env {0}".format(KEY_ONLY_ENV), "config_path": None,
        }
    else:
        chosen_path = DEFAULT_CONFIG_PATH
        try:                              # 默认路径通常在仓库内，展示成相对路径更好读
            shown = str(DEFAULT_CONFIG_PATH.relative_to(REPO))
        except ValueError:                # 被显式改到仓库外时照原样展示，不假装
            shown = str(DEFAULT_CONFIG_PATH)
        source = "default {0}".format(shown)
    if not chosen_path.is_file():
        raise TransportError(
            "未找到凭据文件：{0}（来源 {1}）。本工具**不内置**凭据，也不猜测默认端点；"
            "可设置 {2}、{3}，或提供 --config。".format(chosen_path, source, CONFIG_ENV,
                                                       KEY_ONLY_ENV))
    try:
        data = json.loads(chosen_path.read_text(encoding="utf-8"))
    except Exception as exc:                          # noqa: BLE001
        raise TransportError("凭据文件不可解析：{0}（{1}）".format(chosen_path, exc)) from exc
    if not isinstance(data, dict):
        raise TransportError("凭据文件必须是 JSON 对象：{0}".format(chosen_path))
    profile = data
    if isinstance(data.get("endpoints"), dict):
        name = endpoint or data.get("default_endpoint")
        profiles = data["endpoints"]
        if name not in profiles:
            raise TransportError("凭据文件里没有端点 {0!r}；可用：{1}".format(
                name, sorted(profiles)))
        profile = profiles[name]
    models = profile.get("models") or {}
    resolved_tier = tier or DEFAULT_TIER
    resolved_model = model or models.get(resolved_tier)
    if not resolved_model:
        raise TransportError(
            "无法确定模型：请给 --model，或在凭据文件里为档位 {0!r} 配置 models 映射"
            "（当前可用档位：{1}）".format(resolved_tier, sorted(models)))
    return {
        "base_url": profile.get("base_url") or "",
        "chat_path": profile.get("chat_path") or DEFAULT_CHAT_PATH,
        "api_key": profile.get("api_key") or "",
        "provider": profile.get("provider") or profile.get("kind") or "openai-compatible",
        "models": dict(models),
        "model": resolved_model,
        "tier": resolved_tier,
        "source": source,
        "config_path": str(chosen_path),
    }


def read_private_config(path: Optional[Path]) -> Dict[str, Any]:
    """读私有配置（**只读，不进任何产物**）。

    允许的键：`base_url` / `model` / `api_key` /
    `api_key_env` / `provider`。文件不存在时返回空映射——
    调用方据此给出"凭据缺失"的明确错误，而不是退回某个默认端点。
    """

    if path is None:
        return {}
    path = Path(path)
    if not path.is_file():
        raise TransportError("私有配置不存在：{0}（本工具不猜测默认端点）".format(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                          # noqa: BLE001
        raise TransportError("私有配置不可解析：{0}".format(exc)) from exc
    if not isinstance(data, dict):
        raise TransportError("私有配置必须是 JSON 对象")
    return data


class ApiBackend:
    """OpenAI 兼容 HTTP 后端（真跑；凭据由 resolve_api_credentials 解析）。

    - 凭据只从私有配置或环境读，**绝不落盘**；请求体、响应体与错误文本都经
      `redact()`，落盘前再经 `find_leaked_secrets()` 复核，发现凭据即拒绝写出；
    - **推理型模型**：正文在 `message.content`，思维链在
      `message.reasoning_content`。解析只取 content；思维链只记"存在与否 + 长度"，
      绝不喂给解析器（第三阶段 Lead 实测：`max_tokens` 太小时正文为空、只有思维链）；
    - 失败抛 `TransportError`，**不返回任何伪造回复**。
    """

    origin = ORIGIN_CAPTURED

    def __init__(self, base_url: str, model: str, *, chat_path: str = DEFAULT_CHAT_PATH,
                 api_key: Optional[str] = None,
                 api_key_env: str = DEFAULT_API_KEY_ENV,
                 sampling: Optional[SamplingSpec] = None,
                 timeout_sec: float = DEFAULT_REQUEST_TIMEOUT_SEC,
                 provider: str = "openai-compatible") -> None:
        if not base_url:
            raise TransportError("api 后端必须给出 --base-url 或私有配置里的 base_url")
        if not model:
            raise TransportError("api 后端必须给出 --model/--tier 或私有配置里的 model")
        self.base_url = base_url.rstrip("/")
        self.chat_path = chat_path if chat_path.startswith("/") else "/" + chat_path
        self.model = model
        self.provider = provider
        self.sampling = sampling or SamplingSpec()
        self.timeout_sec = float(timeout_sec)
        self._api_key = api_key or os.environ.get(api_key_env) or ""
        self._api_key_env = api_key_env
        if not self._api_key:
            raise TransportError(
                "未找到凭据：请设置 {0}/{1}，或用私有配置提供 api_key。"
                "本工具**不内置**凭据，也不会把它写进任何产物。".format(
                    api_key_env, KEY_ONLY_ENV))

    @property
    def endpoint(self) -> str:
        return self.base_url + self.chat_path

    @property
    def endpoint_host(self) -> str:
        """**只记主机名**：完整 URL 与查询串不进产物，凭据更不进。"""

        return urllib.parse.urlsplit(self.endpoint).hostname or ""

    def _opener(self):
        """回环地址**绕过代理**（本机实测系统代理会让 127.0.0.1 请求返回 502）。"""

        host = urllib.parse.urlsplit(self.endpoint).hostname or ""
        if host in ("127.0.0.1", "localhost", "::1"):
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    def complete(self, prompt: str) -> ModelReply:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.sampling.temperature is not None:
            body["temperature"] = self.sampling.temperature
        if self.sampling.top_p is not None:
            body["top_p"] = self.sampling.top_p
        if self.sampling.max_tokens is not None:
            body["max_tokens"] = self.sampling.max_tokens
        if self.sampling.seed is not None:
            body["seed"] = self.sampling.seed
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self._api_key},
            method="POST",
        )
        secrets = collect_secrets(self._api_key)
        try:
            with self._opener().open(request, timeout=self.timeout_sec) as response:
                status = response.status
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:                 # 4xx/5xx：明确失败
            detail = redact(exc.read().decode("utf-8", errors="replace")[:500], secrets)
            raise TransportError(
                "模型调用失败：HTTP {0}；响应尾部：{1}".format(exc.code, detail)) from exc
        except Exception as exc:                              # noqa: BLE001 —— 网络层任何异常
            raise TransportError("模型调用失败：{0}".format(redact(str(exc), secrets))) from exc
        try:
            payload = json.loads(raw)
            choices = payload.get("choices") or []
            message = choices[0]["message"]
            # **只取 content**；reasoning_content 是思维链，永远不进解析器。
            text = message.get("content") or ""
            reasoning = message.get("reasoning_content")
            finish_reason = choices[0].get("finish_reason")
        except Exception as exc:                              # noqa: BLE001 —— 结构不符同样是失败
            raise TransportError("模型响应不可解析：{0}".format(
                redact(str(exc), secrets))) from exc
        if not isinstance(text, str):
            raise TransportError("模型响应 content 必须是字符串")
        return ModelReply(
            text=text, backend=BACKEND_API, origin=ORIGIN_CAPTURED,
            provider=self.provider, model=payload.get("model") or self.model,
            captured_at_utc=utc_now(), usage=payload.get("usage") or {},
            http_status=status, finish_reason=finish_reason,
            endpoint_host=self.endpoint_host, model_requested=self.model,
            reasoning_present=None if reasoning is None else True,
            reasoning_chars=None if reasoning is None else len(str(reasoning)),
            info_boundary="strong", usage_source="response_body")


class ReplayBackend:
    """回放后端：读取落盘回复文件，校验来源与提示词哈希后返回原文。"""

    def __init__(self, reply_file: Path, *, prompt_sha256: str) -> None:
        self.envelope = load_reply_envelope(Path(reply_file), prompt_sha256=prompt_sha256)
        self.reply_file = Path(reply_file)

    def complete(self, prompt: str) -> ModelReply:
        data = self.envelope
        return ModelReply(
            text=data["reply"], backend=BACKEND_REPLAY, origin=data["origin"],
            provider=data.get("provider"), model=data.get("model"),
            captured_at_utc=data.get("captured_at_utc"),
            usage=data.get("usage") or {}, finish_reason=data.get("finish_reason"),
            note=data.get("note"), delegator=data.get("delegator"))


class HeadlessBackend:
    """headless 通道：把提示词交给一个**受隔离约束的 DSH 子进程**，取 stdout 当回复。

    纪律（Lead 实测给出、这里逐条落实）：

    1. **stdout = 最终答复**（就是要解析的回复）；**stderr = 推理过程**，
       必须丢弃、绝不喂给解析器（与 api 通道 `reasoning_content` 同一条纪律），
       记录里只留 `stderr_chars` 表示"有多少被丢掉了"；
    2. **工作目录 = mkdtemp()**，并在提示词里追加"只回答、不要用任何工具/读文件"的硬约束；
    3. 子进程环境变量走白名单，只额外注入 `DSH_HOME` 与 `DEEPSEEK_API_KEY`
       （**密钥只注入子进程，不落盘、不进产物**）；
    4. **模型身份是观测值**：调用后读
       `<DSH_HOME>/sessions/**/session.jsonl.zstd` 里 `request/header` 事件的
       `data.header.config`，得到实际使用的 provider/model/reasoningEffort——
       这比"请求里声明了什么"更硬，因为它是**运行痕迹**。
    5. **信息边界弱于 api**：这条通道的运行体具备工作区能力，提示词禁止它用工具，
       但通道本身有该能力。该限制写进每条记录（`info_boundary="weak"`）。
    """

    origin = ORIGIN_HEADLESS

    def __init__(self, *, dsh_bin: str = "dsh", dsh_home: Optional[Path] = None,
                 api_key: str = "", provider: str = "dsh-headless",
                 timeout_sec: float = DEFAULT_HEADLESS_TIMEOUT_SEC,
                 prompt_suffix: str = HEADLESS_PROMPT_SUFFIX,
                 session_before: Optional[set] = None) -> None:
        self.dsh_bin = dsh_bin
        self.dsh_home = Path(dsh_home or DEFAULT_DSH_HOME)
        self._api_key = api_key
        self.provider = provider
        self.timeout_sec = float(timeout_sec)
        self.prompt_suffix = prompt_suffix
        self.prompt_sent: Optional[str] = None
        self.elapsed_sec: Optional[float] = None
        self.stderr_chars: Optional[int] = None
        #: 调用**之前**已存在的会话文件集合：用来定位本次运行新写出的那一个。
        self._session_before = session_before if session_before is not None else set()

    def session_files(self) -> set:
        """`<DSH_HOME>/sessions/**/session.jsonl.zstd` 的当前集合。"""

        root = self.dsh_home / "sessions"
        if not root.is_dir():
            return set()
        return {path for path in root.rglob("session.jsonl.zstd")}

    def complete(self, prompt: str) -> ModelReply:
        import tempfile

        if not self._api_key:
            raise TransportError(
                "headless 通道需要密钥注入子进程：请设置 {0}，或用私有配置提供 api_key".format(
                    KEY_ONLY_ENV))
        full_prompt = prompt + self.prompt_suffix
        self.prompt_sent = full_prompt
        workdir = Path(tempfile.mkdtemp(prefix="sitin-headless-"))
        env = child_env({"DSH_HOME": str(self.dsh_home),
                         KEY_ONLY_ENV: self._api_key})
        try:
            result = process_guard.run_supervised(
                [self.dsh_bin, "--profile", HEADLESS_PROFILE, full_prompt],
                cwd=workdir, timeout_sec=self.timeout_sec, grace_sec=LOAD_TERM_GRACE_SEC,
                env=env)
        finally:
            # GL-4：headless 的临时工作目录同样用完即删（不留垃圾）。
            shutil.rmtree(workdir, ignore_errors=True)
        self.elapsed_sec = result.elapsed_sec
        secrets = collect_secrets(self._api_key)
        if result.timed_out:
            raise TransportError("headless 调用超时：{0} 秒内未结束，已终止进程组（信号 {1}）".format(
                self.timeout_sec, "+".join(result.signals_sent) or "无"))
        if result.returncode != 0:
            tail = redact(result.stderr.strip()[-400:], secrets)
            raise TransportError("headless 调用失败：returncode={0}；stderr 尾部：{1}".format(
                result.returncode, tail))
        text = result.stdout
        self.stderr_chars = len(result.stderr)
        observed, session_file, usage = self._observe_session()
        if not text.strip():
            raise TransportError(
                "headless 返回空 stdout（stderr 有 {0} 字符，可能是推理过程或错误）：不得当合法回复"
                .format(self.stderr_chars))
        return ModelReply(
            text=text.strip(), backend=BACKEND_HEADLESS, origin=ORIGIN_HEADLESS,
            provider=(observed or {}).get("provider") or self.provider,
            model=(observed or {}).get("model"),
            # 用量来自**同一个会话日志**（Lead 实测更正）：assistant/chunk 里
            # data.chunk.type=="usage" 的事件逐条累加。拿不到才是 tokens_unknown。
            captured_at_utc=utc_now(), usage=usage or {},
            usage_source=("session_log" if usage else None),
            http_status=None, finish_reason=None,
            endpoint_host=None, model_requested=None,
            # stderr 是思维链：只记"有多少、被丢弃了"，不喂给解析器。
            reasoning_present=bool(self.stderr_chars),
            reasoning_chars=self.stderr_chars,
            note=("headless 子进程 stdout；stderr({0} 字符)按纪律丢弃；"
                  "信息边界弱于 api 直连（通道具备工作区能力，靠提示词约束）").format(
                      self.stderr_chars),
            observed_config=observed, session_file=session_file,
            elapsed_sec=self.elapsed_sec,
            info_boundary="weak")

    #: 会话日志里用量事件的字段；一个会话可能有**多条**（每个 step 一条）⇒ 累加。
    USAGE_FIELDS: Tuple[str, ...] = ("inputTokens", "outputTokens", "totalTokens",
                                     "cacheReadTokens", "reasoningTokens")

    def _observe_session(self) -> Tuple[Optional[Dict[str, Any]], Optional[str],
                                        Optional[Dict[str, Any]]]:
        """从**运行痕迹**里读模型身份**和真实用量**。

        - 身份：`request/header` → `data.header.config`
          （provider / model / reasoningEffort / maxTokens）；
        - 用量：`assistant/chunk` 事件里 `data.chunk.type == "usage"` 的
          `data.chunk.usage`，**逐条累加**（Lead 实测更正：这条通道的用量拿得到，
          不修的话默认通道就是"花多少看不见"，token 预算账本没法用）。

        观测不到就返回 `(None, None, None)` 并如实落盘——**不猜**：
        身份写成"应该是"比写空更糟；用量确实没有事件时由调用方标 `tokens_unknown`。
        """

        new_files = sorted(self.session_files() - self._session_before,
                           key=lambda path: path.stat().st_mtime)
        if not new_files:
            return None, None, None
        session_file = new_files[-1]
        config: Optional[Dict[str, Any]] = None
        totals: Dict[str, Any] = {field: 0 for field in self.USAGE_FIELDS}
        usage_events = 0
        try:
            decompressed = subprocess.run(["zstd", "-dc", str(session_file)],
                                          capture_output=True, timeout=60)
            if decompressed.returncode != 0:
                return None, str(session_file), None
            for line in decompressed.stdout.decode("utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "request/header" and config is None:
                    found = (event.get("data") or {}).get("header", {}).get("config")
                    if isinstance(found, dict):
                        config = found
                elif event_type == "assistant/chunk":
                    chunk = (event.get("data") or {}).get("chunk") or {}
                    if not isinstance(chunk, dict) or chunk.get("type") != "usage":
                        continue
                    usage = chunk.get("usage") or {}
                    if not isinstance(usage, dict):
                        continue
                    usage_events += 1
                    for field in self.USAGE_FIELDS:
                        value = usage.get(field)
                        if isinstance(value, int) and not isinstance(value, bool):
                            totals[field] += value
        except (OSError, subprocess.SubprocessError):
            return config, str(session_file), None
        if not usage_events:
            return config, str(session_file), None
        totals["events"] = usage_events
        return config, str(session_file), totals


class DelegateBackend:
    """委派后端：**本进程不与模型通信**，只做文件式交接。

    为什么不在工具内部调用外部代理：Python 侧没有子代理 API，也不该有——
    工具一旦能自己"创造"一个模型回复，血缘里"这条回复是谁产的"就再也说不清。
    因此这里只提供两个动作：`emit`（产出提示词交接件）与 `ingest`（摄入回复文件）。
    """

    origin = ORIGIN_DELEGATED

    def complete(self, prompt: str) -> ModelReply:
        raise TransportError(
            "delegate 后端不与模型直接通信：请先用 --emit-prompt 产出交接件、"
            "交给生成方，再用 --ingest-reply <文件> 摄入回复。")


def load_reply_envelope(path: Path, *, prompt_sha256: str) -> Dict[str, Any]:
    """读取并**严格校验**落盘回复文件；任何一项不符即拒绝。

    校验项（缺一不可）：
      1. schema 名正确；
      2. `origin` 在枚举内；
      3. 该来源要求的字段齐备且非空；
      4. `format_fixture` **不得**携带 provider/model ——
         否则就是"把人工夹具写成模型输出"，直接拒绝；
      5. `prompt_sha256` 与本次提示词**逐字节**一致。
    """

    path = Path(path)
    if not path.is_file():
        raise ReplyEnvelopeError("回复文件不存在：{0}".format(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                          # noqa: BLE001
        raise ReplyEnvelopeError("回复文件不可解析：{0}".format(exc)) from exc
    if not isinstance(data, dict):
        raise ReplyEnvelopeError("回复文件必须是 JSON 对象")
    if data.get("schema") != REPLY_FILE_SCHEMA:
        raise ReplyEnvelopeError("回复文件 schema 必须是 {0}，得到 {1!r}".format(
            REPLY_FILE_SCHEMA, data.get("schema")))
    origin = data.get("origin")
    if origin not in ORIGINS:
        raise ReplyEnvelopeError("origin 必须是 {0} 之一，得到 {1!r}".format(
            list(ORIGINS), origin))
    missing = [key for key in _ORIGIN_REQUIRED[origin] if not data.get(key)]
    if missing:
        raise ReplyEnvelopeError("origin={0} 缺少必填字段：{1}".format(origin, "、".join(missing)))
    if not isinstance(data.get("reply"), str) or not data["reply"].strip():
        raise ReplyEnvelopeError("reply 必须是非空字符串")
    if origin == ORIGIN_FIXTURE and (data.get("provider") or data.get("model")):
        raise ReplyEnvelopeError(
            "origin=format_fixture 不得携带 provider/model：人工夹具不是模型输出")
    if data.get("prompt_sha256") != prompt_sha256:
        raise ReplyEnvelopeError(
            "提示词哈希不符：文件记 {0}，本次提示词是 {1}。"
            "**不接受**把另一次回复当作本次回复。".format(
                short(data.get("prompt_sha256")), short(prompt_sha256)))
    return data


def build_backend(kind: str, *, prompt_sha256: str, reply_file: Optional[Path] = None,
                  base_url: Optional[str] = None, model: Optional[str] = None,
                  config: Optional[Path] = None, api_key_env: str = DEFAULT_API_KEY_ENV,
                  sampling: Optional[SamplingSpec] = None,
                  timeout_sec: float = DEFAULT_REQUEST_TIMEOUT_SEC,
                  endpoint: Optional[str] = None, tier: Optional[str] = None,
                  dsh_bin: str = "dsh",
                  dsh_home: Optional[Path] = None):
    """按后端名构造后端；**缺参即报错，不静默退化到别的通道**。"""

    if kind == BACKEND_DELEGATE:
        return DelegateBackend()
    if kind == BACKEND_REPLAY:
        if reply_file is None:
            raise TransportError("replay 后端必须给出 --replay/--reply-file")
        return ReplayBackend(Path(reply_file), prompt_sha256=prompt_sha256)
    if kind == BACKEND_API:
        creds = resolve_api_credentials(config, endpoint=endpoint, model=model, tier=tier,
                                        api_key_env=api_key_env)
        backend = ApiBackend(
            base_url or creds["base_url"], creds["model"] or "",
            chat_path=creds["chat_path"], api_key=creds["api_key"] or None,
            api_key_env=api_key_env, sampling=sampling, timeout_sec=timeout_sec,
            provider=creds["provider"] or "openai-compatible")
        # 凭据**来源**可以进产物（它是"哪来的"，不是密钥本身）。
        backend.credential_source = creds["source"]           # type: ignore[attr-defined]
        backend.tier = creds["tier"]                          # type: ignore[attr-defined]
        return backend
    if kind == BACKEND_HEADLESS:
        creds = resolve_api_credentials(config, endpoint=endpoint, model=model, tier=tier,
                                        api_key_env=api_key_env)
        backend = HeadlessBackend(
            dsh_bin=dsh_bin, dsh_home=dsh_home, api_key=creds["api_key"] or "",
            timeout_sec=timeout_sec if timeout_sec != DEFAULT_REQUEST_TIMEOUT_SEC
            else DEFAULT_HEADLESS_TIMEOUT_SEC)
        backend.credential_source = creds["source"]           # type: ignore[attr-defined]
        return backend
    raise TransportError("未知后端：{0!r}".format(kind))


# ============================================================ 4. 解析（固定结构：thought + code）

@dataclass(frozen=True)
class ParsedReply:
    """把模型回复切成固定结构；**只有 `status == ok` 才允许进入装载**。"""

    status: str
    thought: Optional[str]
    code: Optional[str]
    problems: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == PARSE_OK

    def to_json(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "thought": self.thought,
            "thought_chars": len(self.thought or ""),
            # 与落盘的 candidate.py **同一口径**：解析产物、记录与文件三处的哈希必须一致
            # （否则读的人会以为候选与自己不是同一份，实测踩过一次同类问题）。
            "code_sha256": sha256_text(normalized_code(self.code)) if self.code else None,
            "code_chars": len(self.code or ""),
            "problems": list(self.problems),
        }


_FENCE_RE = re.compile(r"^[ \t]*" + FENCE + r"[ \t]*[A-Za-z0-9_+-]*[ \t]*\n(.*?)^[ \t]*"
                       + FENCE + r"[ \t]*$", re.DOTALL | re.MULTILINE)

#: 入口函数的**定义**：候选代码块的判据是「块内定义了入口函数」，不是「块内出现过入口函数名」。
#: P25 小诊断抓到的测量缺陷（阻塞级）：四字段 JSON 的 trigger 里写了 score_actions ⇒ 旧口径
#: （子串命中）把机制说明块也当成候选 ⇒ ambiguous_code ⇒ 整题误拒；机制说明写得越细越容易被
#: 判挂。判据换成"定义了入口函数"之后，机制说明块无论怎么写都不会被当成候选。
AV_ENTRY_DEF_RE = re.compile(r"(?m)^[ \t]*def[ \t]+" + re.escape(AV_ENTRY_NAME) + r"[ \t]*\(")


def fence_language(match) -> str:
    """围栏的语言标注（json / python / 空）——取自开围栏那一行，小写。"""

    head = match.group(0).lstrip()
    if not head.startswith(FENCE):
        return ""
    return head[len(FENCE):].split("\n", 1)[0].strip().lower()


def av_block_is_mechanism_json(body: str) -> bool:
    """块体本身就是 JSON 对象（四字段机制说明块）——不论有没有 json 标注。

    判据是**内容**（可被 json.loads 解析为对象），不是"看起来像"；Python 候选源码不会解析
    成 JSON 对象，因此不会误伤候选。
    """

    stripped = (body or "").strip()
    if not stripped.startswith("{"):
        return False
    try:
        data = json.loads(stripped)
    except ValueError:
        return False
    return isinstance(data, Mapping)


def av_candidate_block_indices(blocks, languages) -> List[int]:
    """候选代码块的定义式判据（替代「块内出现过入口函数名」的子串判据）。

    候选 = 语言标注不是 json、块体不是 JSON 对象、且块内**定义了**入口函数的块。
    只有说明文字、只有四字段 JSON、只有散文的块一律**不是**候选。
    """

    picked: List[int] = []
    for index, body in enumerate(blocks):
        if (languages[index] if index < len(languages) else "") == "json":
            continue
        if av_block_is_mechanism_json(body):
            continue
        if AV_ENTRY_DEF_RE.search(body or ""):
            picked.append(index)
    return picked


def normalized_code(code: str) -> str:
    """落盘与被哈希的代码文本：去掉尾部空行、以**恰好一个**换行结束。

    三处必须同源：`parsed.json` 的 code_sha256、`record.json` 的 code.sha256、
    `candidate.py` 的字节哈希。初版一处用原始文本、一处用规范化文本，
    父代核验因此在"同一份代码"上拒绝（与 R8-5 的产物/台账不一致同类）。
    """

    return code.rstrip("\n") + "\n"


def _first_braced_span(text: str) -> Optional[Tuple[str, int, int]]:
    """取**第一个配平**的 {…} 跨度，返回 (内容, 起始, 结束)；不配平返回 None。

    返回结束位置是给"没有代码围栏"的情形用的：那时整段代码要从**说明之后**取，
    从入口函数取会丢掉 import，候选将无法装载。
    """

    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index].strip(), start, index + 1
    return None


def parse_model_reply(raw: str, entry_name: str = ENTRY_NAME, *,
                       require_entry_definition: bool = False) -> ParsedReply:
    """解析回复：框内一句话是「思想」，唯一代码块是「代码」。

    解析**不做善意猜测**：找不到思想、找不到代码、出现多个互斥代码块，
    都按各自的拒绝状态返回，并把问题逐条写明——猜测会把"格式不合格"
    悄悄变成"看起来能用"。

    require_entry_definition=True（AV 生成题走这条路）时，候选代码块的判据从「块内出现过入口
    函数名」换成「块内**定义了**入口函数」（见 av_candidate_block_indices）。没有候选块时
    **逐字沿用**旧的三分支判定（不放宽、不静默接受）：旧口径能拒的仍然拒。默认 False 时本
    函数行为与改动前逐字节一致（其它判分路径不受影响）。
    """

    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        return ParsedReply(PARSE_EMPTY, None, None, ("回复为空",))
    problems: List[str] = []
    matches = list(_FENCE_RE.finditer(text))
    spans = [(match.start(), match.group(1).strip()) for match in matches]
    entry_index = text.find("def " + entry_name)
    # **机制说明只允许出现在代码之前**（EoH 格式：先说机制，再给代码）。
    # 初版在全文里找第一个 {...}，于是把代码里的 "{0}" 当成了机制说明，
    # 一条本该被拒绝的回复（没有说明）被判成 ok——夹具反例当场暴露了它。
    head_end = spans[0][0] if spans else (entry_index if entry_index >= 0 else len(text))
    span = _first_braced_span(text[:head_end])
    thought = span[0] if span else None
    if thought is None:
        problems.append("代码之前未找到花括号 {…} 内的机制说明")
    blocks = [body for _start, body in spans]
    code: Optional[str] = None
    ambiguous = False
    candidate_indices: Optional[List[int]] = None
    if spans and require_entry_definition:
        candidate_indices = av_candidate_block_indices(
            blocks, [fence_language(match) for match in matches])
    if spans:
        if candidate_indices is not None and len(candidate_indices) == 1:
            # AV 新口径：恰好一个块**定义了**入口函数 ⇒ 它就是候选（机制说明块不参与）。
            code = blocks[candidate_indices[0]]
        elif candidate_indices is not None and len(candidate_indices) > 1:
            ambiguous = True
            problems.append("有 {0} 个代码块都定义了入口函数 {1}，无法确定用哪一个".format(
                len(candidate_indices), entry_name))
        else:
            # 旧口径（逐字未改，不因新判据放宽）：含入口名的块；没有则单块；多块即 ambiguous。
            with_entry = [block for block in blocks if entry_name in block]
            if len(with_entry) == 1:
                code = with_entry[0]
            elif len(with_entry) > 1:
                ambiguous = True
                problems.append("有 {0} 个代码块都包含入口函数，无法确定用哪一个".format(
                    len(with_entry)))
            elif len(blocks) == 1:
                code = blocks[0]
            else:
                ambiguous = True
                problems.append("有 {0} 个代码块且都不含入口函数，无法确定用哪一个".format(
                    len(blocks)))
    elif entry_index >= 0:
        # 没有围栏：退化为"从机制说明之后到结尾"的整段（**保留 import**，
        # 否则候选装不上）；仍然要求入口真实存在。
        code = text[span[2]:].strip() if span else text[entry_index:].strip()
    else:
        problems.append("未找到代码块，也未找到入口函数定义")
    if thought is None:
        status = PARSE_MISSING_THOUGHT
    elif code is None and ambiguous:
        status = PARSE_AMBIGUOUS_CODE
    elif code is None:
        status = PARSE_MISSING_CODE
    else:
        status = PARSE_OK
    return ParsedReply(status, thought, code, tuple(problems))


# ============================================================ 5. 静态扫描（子进程外快速拒绝）

@dataclass(frozen=True)
class ScanReport:
    """静态扫描结论；**它不是门禁结论**，只决定"要不要花一次隔离装载"。"""

    ok: bool
    problems: Tuple[str, ...]
    imports: Tuple[str, ...]
    entry_present: bool

    def to_json(self) -> Dict[str, Any]:
        return {"ok": self.ok, "problems": list(self.problems),
                "imports": list(self.imports), "entry_present": self.entry_present}


def _module_allowed(module: str) -> bool:
    """`import X` 只有**精确命中**白名单模块才放行。

    初版用"白名单里有没有以 X 开头的模块"（前缀匹配）判断，于是
    `import hangma_bot.policy`、`from hangma_bot import policy` 都能通过——
    而 `hangma_bot.policy` 的子模块里就有候选注册表 `policy.heuristics`，
    白名单被"先导入父包"绕开（第三阶段 Challenger #8）。导入父包即执行它的
    `__init__` 并带进一批不在允许面内的实现，这条路径不该由生成代码打开。
    """

    return bool(module) and module in ALLOWED_IMPORTS


def _from_alias_allowed(module: str, alias: str) -> bool:
    """`from X import a`：要么 X 本身是白名单模块（a 是它的属性或星号），
    要么 `X.a` **精确**是白名单模块。

    这样 `from hangma_bot.policy import heuristics` 被拒（`policy.heuristics` 不在白名单），
    而 `from hangma_bot.policy import heuristic_adapter, evaluation_v1` 仍然合法。
    """

    if module in ALLOWED_IMPORTS:
        return True
    combined = (module + "." + alias) if module else alias
    return combined in ALLOWED_IMPORTS


#: 入口函数的两个位置参数名与顺序（函数合同的一部分；改它属接口变更）。
ENTRY_PARAMS: Tuple[str, ...] = ("params", "source_fingerprint_value")


def check_entry_signature(tree: ast.Module) -> Tuple[bool, List[str]]:
    """核验**入口函数签名**：必须是**顶层**函数，参数名与默认值符合函数合同。

    为什么要在静态阶段就查：初版只查"有没有这个名字的 FunctionDef"，
    于是 **嵌套定义**、**改了参数名**、**少了默认值**都能过——README 却把"入口签名"
    记在静态扫描账上，属于"口径写得比机制强"（第三阶段 Challenger #8 的连带项）。
    这里只做静态可判的部分；**可调用性、返回值类型与真实行为由隔离装载阶段验证**。
    """

    problems: List[str] = []
    top_level = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name == ENTRY_NAME]
    if not top_level:
        return False, ["缺少**顶层**入口函数 {0}（不允许嵌套定义）".format(ENTRY_NAME)]
    if len(top_level) > 1:
        return False, ["顶层定义了 {0} 个 {1}，无法确定用哪一个".format(
            len(top_level), ENTRY_NAME)]
    function = top_level[0]
    positional = list(function.args.posonlyargs) + list(function.args.args)
    names = [arg.arg for arg in positional]
    if tuple(names[: len(ENTRY_PARAMS)]) != ENTRY_PARAMS:
        problems.append("入口参数名/顺序不符：期望 {0}，实际 {1}".format(
            list(ENTRY_PARAMS), names))
    if len(positional) != len(ENTRY_PARAMS):
        problems.append("入口位置参数个数不符：期望 {0} 个，实际 {1} 个".format(
            len(ENTRY_PARAMS), len(positional)))
    if len(function.args.defaults) < len(positional) - 1:
        problems.append("入口第二个参数必须有默认值（source_fingerprint_value: str = \"\"）")
    return (not problems), problems


def scan_generated_code(code: str) -> ScanReport:
    """语法 + 白名单 + 禁止痕迹的**静态 lint**（不执行代码）。

    **它是 lint，不是边界**（Lead 裁定 #4/#9）：任何静态检查都能被
    `getattr(__builtins__, "op" + "en")` 这类写法绕过，因此这里只做
    "快速拒绝明显不合格的输入"，省下一次隔离装载。**真正的边界是隔离装载**：
    子进程 + mkdtemp 工作目录 + 环境变量白名单 + 注册表前后哈希快照。

    本清单与门禁 G-1 的清单**不共用实现、也没有一致性回归**（当前各 26 项 / 16 项），
    因此不得声称"同源"。
    """

    problems: List[str] = []
    imports: List[str] = []
    entry_present = False
    for token in FORBIDDEN_TOKENS:
        if token in code:
            problems.append("命中禁止痕迹：{0!r}".format(token))
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return ScanReport(False, tuple(problems + ["语法错误：第 {0} 行 {1}".format(
            exc.lineno, exc.msg)]), tuple(imports), False)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                if not _module_allowed(alias.name):
                    problems.append("禁止的 import：{0}".format(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append("禁止相对 import（生成的模块按文件独立装载）")
                continue
            module = node.module or ""
            imports.append(module)
            for alias in node.names:
                combined = "{0}.{1}".format(module, alias.name) if module else alias.name
                imports.append(combined)
                if not _from_alias_allowed(module, alias.name):
                    problems.append("禁止的 import：from {0} import {1}".format(
                        module or "<相对包>", alias.name))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                problems.append("禁止的调用：{0}()".format(node.func.id))
    _signature_ok, signature_problems = check_entry_signature(tree)
    problems.extend(signature_problems)
    entry_present = _signature_ok
    if not entry_present:
        problems.append("缺少入口函数 {0}".format(ENTRY_NAME))
    return ScanReport(not problems, tuple(problems), tuple(sorted(set(imports))), entry_present)


# ============================================================ 7. 写盘账本与 --out 守卫

def _is_under(path: Path, root: Path) -> bool:
    """path 是否等于 root 或位于 root 之下（两侧都先 resolve）。"""

    resolved_path = Path(path).resolve()
    resolved_root = Path(root).resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def guard_out_dir(out_dir: Path) -> Path:
    """拒绝把产物写进**受控源码树**、版本库元数据或仓库根。

    为什么要有这道守卫：工具的纪律是"只写 `--out`"，但纪律若只写在文档里，
    一次手滑的 `--out src/hangma_bot/policy/heuristics` 就能把生成代码落进候选注册表目录，
    而注册表目录正是"人工审核后才准改"的地方（README §17 的静态注册合同）。
    守卫让"越界"在**写第一个字节之前**就失败。
    """

    resolved = Path(out_dir).resolve()
    # 注意：**不能**用"是否在仓库内"判断——证据目录本来就在仓库里。
    # 只拦三类：仓库根自身、受控源码树 src/、版本库元数据 .git/。
    if resolved == REPO.resolve():
        raise ValueError("--out 不得指向仓库根：{0}。本工具只写自己的产物目录。".format(resolved))
    for root, why in ((_project_file(_PROJECT_ROOT, REPO / "src"), "受控源码树 src/"), (_project_file(_PROJECT_ROOT, REPO / ".git"), "版本库元数据 .git/")):
        if _is_under(resolved, root):
            raise ValueError(
                "--out 不得指向{0}：{1}。本工具只写自己的产物目录；"
                "把生成代码写进候选注册表目录等于绕过人工审核与静态注册。".format(why, resolved))
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("--out 已存在且不是目录：{0}".format(resolved))
    return resolved


class WriteLedger:
    """本次运行**实际写出的路径**账本（记录，不是断言）。

    三条硬边界里的 `wrote_to_src=false` 初版是**硬编码常量**——那等于自称，
    不是证据（第三阶段 Challenger #11/#13）。现在所有产物写盘都经本类，
    记录里落的 `writes` 段就是"实际写出的路径清单"，并可逐条核验是否都在 `--out` 下。
    系统临时目录下的中间文件（隔离装载的子进程报告）不进清单：它们不是证据产物。
    """

    def __init__(self, out_dir: Path, secrets: Sequence[str] = ()) -> None:
        self.out_dir = Path(out_dir).resolve()
        self.paths: List[str] = []
        #: 凭据明文集合：**每次写盘前**复核，命中即拒绝写出（GL-2）。
        #: 初版只在 record dict 上复核，而 prompt.txt/reply_raw.txt/candidate.py/
        #: records.jsonl/budget.json/summary.md 都是直写的——复核等于没做。
        self.secrets: Tuple[str, ...] = tuple(secrets)

    def record(self, path: Path) -> None:
        self.paths.append(str(Path(path).resolve()))

    def _guard(self, path: Path, text: str) -> None:
        leaks = find_leaked_secrets(text, self.secrets)
        if leaks:
            raise ValueError(
                "检出凭据明文（指纹 {0}）：拒绝写出 {1}".format(leaks, path))

    def write_text(self, path: Path, text: str) -> None:
        path = Path(path)
        self._guard(path, text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.record(path)

    def write_json(self, path: Path, payload: Any) -> None:
        self.write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def append_text(self, path: Path, text: str) -> None:
        path = Path(path)
        self._guard(path, text)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
        self.record(path)

    def to_json(self) -> Dict[str, Any]:
        """把账本变成**可核验**的结论：逐条判是否在 --out 下、是否碰到 src/。"""

        # 同一路径可能被写多次（例如 record.json 在回填写盘账本后再写一次），
        # 清单按**去重后的实际路径集合**给出。
        unique = sorted(set(self.paths))
        outside = [item for item in unique if not _is_under(Path(item), self.out_dir)]
        relative = sorted(
            str(Path(item).relative_to(self.out_dir)) for item in unique
            if _is_under(Path(item), self.out_dir))
        registry = _project_file(_PROJECT_ROOT, REPO / "src" / "hangma_bot" / "policy" / "heuristics")
        registry_touched = [item for item in unique if _is_under(Path(item), registry)]
        return {
            "out_dir": str(self.out_dir),
            "artifact_writes": len(unique),
            "paths": relative,
            "outside_out": outside,
            "all_under_out": not outside,
            "src_touched": bool([item for item in unique
                                 if _is_under(Path(item), _project_file(_PROJECT_ROOT, REPO / "src"))]),
            "registry_dir_touched": bool(registry_touched),
            "how": ("所有产物写盘都经 WriteLedger：本清单就是本次运行实际写出的路径；"
                    "系统临时目录下的隔离装载报告不计入（它不是证据产物）"),
        }


def _write_json(path: Path, payload: Any, writes: Optional[WriteLedger] = None,
                secrets: Sequence[str] = ()) -> None:
    """写 JSON 产物：**始终经 WriteLedger**（GL-10 的结构约束：没有第二条写盘路径）。

    没有传入账本时就地建一个（产物目录取该文件所在目录），这样
    "所有写盘目标都由 WriteLedger 记录"这条约束在结构上成立，而不是靠自觉。
    """

    ledger = writes if writes is not None else WriteLedger(Path(path).parent, secrets=secrets)
    ledger.write_json(path, payload)


def info_boundary_block(strength: Optional[str], backend: str) -> Dict[str, Any]:
    """信息边界：**只在工具自己发出过请求**时才谈得上强弱。

    - `headless` → `weak`：运行体具备工作区能力，只能靠提示词约束；
    - `api` → `strong`：直连 HTTP，没有工具与文件访问能力；
    - `delegate` / `replay`（含人工夹具）→ `n/a`：
      工具**没有发出任何请求**，回复来自落盘文件，边界强弱不是本工具可断言的事
      （该说的在 `provenance_attestation` 里：封套是自述、夹具是人写的）。
    """

    if backend == BACKEND_HEADLESS or strength == "weak":
        return {"strength": "weak",
                "note": ("headless 通道的运行体具备工作区能力；提示词已要求只回答、"
                         "不使用任何工具、不读取文件，但该约束是**提示词级**的，弱于 api 直连")}
    if backend == BACKEND_API:
        return {"strength": "strong", "note": "api 直连：无工具、无文件访问能力"}
    return {"strength": "n/a",
            "note": ("本通道**没有向模型发出请求**（回复来自落盘文件或人工夹具），"
                     "因此不声明工具/文件边界；取证强度见 provenance_attestation")}


def admission_block(*, code_sha256: Optional[str], registered: bool,
                    gate_hits: List[str], as_of: str) -> Dict[str, Any]:
    """准入状态：**带 as-of 与出处的实际检查结果**，不是写死的永久常量。

    第三阶段 Challenger 指出两处问题并要求更正：
      ① 初版把"3.P 未收口"写死进每条产物——那是**当时的**事实，不是永久事实
         （3.P 已由 fixverify 包交付 ver 1）。阻塞原因必须写成"**当前**还差什么"；
      ② `eligible=false` 若只是常量，读的人无法判断它是否还成立。

    因此本函数只接受**查出来的**结果（注册表里有没有同源码文件、有没有该候选的门禁记录），
    并把"无机器可核验项"（人工审核）显式标成 `checked=false`。
    """

    blocking = ["未进入 policy/heuristics 静态注册表（无静态注册表行 ⇒ 门禁与调度都找不到它）"]
    if not registered:
        blocking.append("已核对注册表目录：其中没有任何文件与本次候选源码逐字节相同")
    if not gate_hits:
        blocking.append("已核对门禁记录：没有一条记录指向本次候选源码（G-1/G-2/G-3 未跑）")
    blocking.append("无机器可核验的人工审核标记：人审由发布流程签字，本工具不代签")
    blocking.append("无桌赛与阶段证据（本工具不跑桌赛，也不产出效果结论）")
    return {
        "eligible": False,
        "status": "pending_admission",
        "as_of_utc": as_of,
        "checks": {
            "registry_source_match": {
                "checked": True,
                "value": registered,
                "how": ("把候选源码的 sha256 与 src/hangma_bot/policy/heuristics/*.py "
                        "逐个比对；命中即说明同一份代码已在注册表目录里"),
            },
            "gate_records_for_source": {
                "checked": True,
                "value": gate_hits,
                "how": ("在 evidence/2.3-gates/ 的 *.json 里按 source_sha256 / "
                        "candidate_identity 搜本次候选源码哈希"),
            },
            "human_review": {
                "checked": False,
                "value": None,
                "how": "没有可机器核验的人工审核标记；不得由本工具代签",
            },
        },
        "blocking": blocking,
        "unfreeze_path": [
            "① 人工审核候选机制与源码",
            "② 在 src/hangma_bot/policy/heuristics/ 增加模块并在 CANDIDATE_FACTORIES 加一行（静态注册）",
            "③ 用 tools/sitin_gates.py 跑 G-1/G-2/G-3 并留下准入记录",
            "④ 按冻结面板跑桌赛/阶段比较（本工具不产出这一步的结论）",
        ],
        "note": "装载成功只是 G-0 同级结论，不等于准入；不得据此进入效果评估",
    }


def probe_registry_source(code_sha256: Optional[str],
                         registry_before: Optional[Mapping[str, str]] = None
                         ) -> Tuple[bool, List[str]]:
    """实际去查：注册表目录里有没有与本次候选**逐字节相同**的源码；门禁记录有没有指向它。

    `registry_before` 是**装载前**的快照：这样"是否已注册"不受装载期间的写入影响
    （装载期间发生的任何变化由 `supervised_load` 的前后快照比对单独判失败）。
    """

    registered = False
    if code_sha256 and registry_before is not None:
        registered = code_sha256 in set(registry_before.values())
    elif code_sha256:
        registry = _project_file(_PROJECT_ROOT, REPO / "src" / "hangma_bot" / "policy" / "heuristics")
        for path in sorted(registry.glob("*.py")):
            try:
                if sha256_file(path) == code_sha256:
                    registered = True
                    break
            except OSError:
                continue
    gate_hits: List[str] = []
    if code_sha256:
        gates_dir = _project_file(_PROJECT_ROOT, REPO / "review" / "llm-guided-heuristic-route-2026-09-15" / "evidence" / "2.3-gates")
        for path in sorted(gates_dir.rglob("*.json")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if code_sha256 in text:
                gate_hits.append(str(path.relative_to(REPO)))
    return registered, gate_hits


# ============================================================ 8. 隔离装载（G-0 同级）

@dataclass(frozen=True)
class LoadOutcome:
    """隔离装载结局；`ok=False` 时 `reason` 必非空。"""

    ok: bool
    reason: str = ""
    report: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "gate_level": "G-0 同级（受监管装载与构造）",
            "equivalent_to_three_gates": False,
            "gates_run": [],
            "report": self.report,
            "execution": self.execution,
        }


def synthetic_facts_probe(adjustment) -> Dict[str, Any]:
    """**事实完整**的合成窗口探针：补上"冷启动探针零判别力"那一刀（GL-5）。

    冷启动探针用的是 `facts=None`，候选只要在入口处判一下"事实缺失就返回 0.0"
    就能全绿——它证明不了任何机制会生效。这里构造一个**事实完整**的合成窗口：

      - 窗口内一个吃候选（`HAND_PROGRESS` + `COMPLETE` + `shanten_after=1`）
        与一个**过牌参考候选**（同样事实完整、`shanten_after=2`）；
      - 于是"动作前/动作后"两侧都有可用事实，读事实的分支会被真正走到。

    **它仍然不是规则事实覆盖**：合成窗口只有两个候选、没有牌河与副牌，
    因此只能说明"机制在当前作用面上会算出有限、确定的分数"，
    真正的覆盖与行为诊断仍属 G-1/G-2。判别力标签写 `mechanism_reachable`。
    """

    from hangma_bot.hangma.interface import (
        CandidateFactKind,
        CandidateFacts,
        RuleCandidate,
        RuleCompleteness,
    )
    from hangma_bot.kernel.actions import Pass
    from hangma_bot.policy.evaluation_v1 import EvaluationContext, ScoredCandidate

    result: Dict[str, Any] = {
        "probe": "synthetic_complete_facts",
        "discriminative_power": "mechanism_reachable",
        "coverage": ("合成事实完整窗口（COMPLETE + HAND_PROGRESS，含过牌参考态）："
                     "证明读事实的分支会被走到、delta 有限且确定；"
                     "**不**构成规则事实覆盖或 G-1/G-2 结论"),
        "cases": [],
    }
    facts_after = CandidateFacts(fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=1,
                                 completeness=RuleCompleteness.COMPLETE)
    facts_before = CandidateFacts(fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=2,
                                  completeness=RuleCompleteness.COMPLETE)
    reference = RuleCandidate(action=Pass(), action_key="pass", evidence=(),
                              facts=facts_before)
    context = EvaluationContext(
        combined_codes=("1w", "2w", "3w"), wealth_code="白", safe_codes=frozenset(),
        my_seat=0, next_seat=1, next_seat_meld_codes=(), dealer_seat=0,
        dealer_meld_codes=(), table_rank=1, catch_play=False, chain_count=1, baotou=False,
        wealth_count=0, chain_piao=0)
    for key in probe_window_keys(adjustment.spec.scope):
        candidate = RuleCandidate(action=Pass(), action_key=key, evidence=(),
                                  facts=facts_after)
        item = ScoredCandidate(priority=1, candidate=candidate, action_key=key,
                               parts=(), reasons=(), total=0.0, shanten=1,
                               is_safe_discard=False)
        case: Dict[str, Any] = {"action_key": key}
        try:
            first = adjustment.apply(item, context, (candidate, reference))
            second = adjustment.apply(item, context, (candidate, reference))
            case["total_first"] = first.total
            case["total_second"] = second.total
            case["parts"] = [{"name": part.name, "value": part.value} for part in first.parts]
            case["delta"] = first.total - item.total
            case["deterministic"] = (first.total == second.total
                                     and first.parts == second.parts)
            case["finite"] = math.isfinite(first.total)
            if not case["deterministic"]:
                case["error"] = "同输入两次调用结果不同（候选不得持有可变状态）"
            elif not case["finite"]:
                case["error"] = "调整后评分非有限"
        except Exception as exc:                          # noqa: BLE001 —— 任何异常都算失败
            case["error"] = "{0}: {1}".format(type(exc).__name__, exc)
        result["cases"].append(case)
    result["ok"] = all("error" not in case for case in result["cases"])
    # 判别力证据：至少有一个窗口的 delta 非零 ⇒ 机制在作用面上**确实被走到**
    result["mechanism_fired"] = any(abs(case.get("delta") or 0.0) > 0.0
                                    for case in result["cases"])
    return result


def probe_window_keys(scope: Sequence[str]) -> Tuple[str, ...]:
    """冷启动探针用的动作键：作用面内的前两类各一个，外加 `pass`。"""

    keys = ["{0}:1w".format(kind) for kind in scope[:2] if kind != "pass"]
    keys.append("pass")
    return tuple(dict.fromkeys(keys))


def cold_start_probe(adjustment) -> Dict[str, Any]:
    """**冷启动探针**：在空事实窗口上调用候选，确认不抛异常且同输入同输出。

    覆盖范围的边界必须说清：这里 `facts=None`、只有一个候选，
    因此它**只**证明「入口能跑、空事实路径不炸、两次调用一致」；
    真正的规则事实覆盖与行为诊断属于 G-1/G-2（不在这里，也不在本轮）。
    """

    from hangma_bot.hangma.interface import RuleCandidate
    from hangma_bot.kernel.actions import Pass
    from hangma_bot.policy.evaluation_v1 import EvaluationContext, ScoredCandidate

    candidate = RuleCandidate(action=Pass(), action_key="pass", evidence=(), facts=None)
    context = EvaluationContext(
        combined_codes=(), wealth_code="1w", safe_codes=frozenset(), my_seat=0, next_seat=1,
        next_seat_meld_codes=(), dealer_seat=0, dealer_meld_codes=(), table_rank=1,
        catch_play=False)
    result: Dict[str, Any] = {"probe": "cold_start_no_facts", "cases": [],
                              "discriminative_power": "smoke_only",
                              "coverage": ("仅空事实窗口（facts=None 的早退分支）：证明入口可调用、"
                                           "不抛异常、两次调用一致；**不**构成 G-1/G-2/G-3 覆盖。"
                                           "它判不出候选机制是否真的会生效——见同目录的 "
                                           "synthetic_complete_facts 探针")}
    for key in probe_window_keys(adjustment.spec.scope):
        item = ScoredCandidate(priority=1, candidate=candidate, action_key=key,
                               parts=(), reasons=(), total=0.0, shanten=None,
                               is_safe_discard=False)
        case: Dict[str, Any] = {"action_key": key}
        try:
            first = adjustment.apply(item, context, (candidate,))
            second = adjustment.apply(item, context, (candidate,))
            case["total_first"] = first.total
            case["total_second"] = second.total
            case["parts"] = [{"name": part.name, "value": part.value}
                             for part in first.parts]
            case["deterministic"] = (first.total == second.total
                                     and first.parts == second.parts)
            case["finite"] = math.isfinite(first.total)
            if not case["deterministic"]:
                case["error"] = "同输入两次调用结果不同（候选不得持有可变状态）"
            elif not case["finite"]:
                case["error"] = "调整后评分非有限"
        except Exception as exc:                          # noqa: BLE001 —— 任何异常都算失败
            case["error"] = "{0}: {1}".format(type(exc).__name__, exc)
        result["cases"].append(case)
    result["ok"] = all("error" not in case for case in result["cases"])
    return result


#: 隔离装载子进程的**环境变量白名单**：不再把 dict(os.environ) 整个传下去。
#: 理由（Lead 裁定 #9）：静态扫描是 lint，**不是边界**；边界是"子进程 + 最小环境 +
#: 工作目录隔离 + 装载前后对注册表取哈希快照"。整份环境传下去等于把父进程的
#: PATH/凭据/配置一起交到生成代码手里。
CHILD_ENV_ALLOWLIST: Tuple[str, ...] = (
    "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM", "SHELL", "USER",
)

#: 注册表目录（装载前后取快照的对象）。
REGISTRY_DIR = _project_file(_PROJECT_ROOT, REPO / "src" / "hangma_bot" / "policy" / "heuristics")


def child_env(extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """构造子进程环境：**白名单 + 显式注入**，其余一律不带。"""

    env = {key: os.environ[key] for key in CHILD_ENV_ALLOWLIST if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def registry_snapshot() -> Dict[str, str]:
    """候选注册表目录的逐文件哈希快照（装载前后各取一次）。"""

    snapshot: Dict[str, str] = {}
    if not REGISTRY_DIR.is_dir():
        return snapshot
    for path in sorted(REGISTRY_DIR.glob("*.py")):
        try:
            snapshot[path.name] = sha256_file(path)
        except OSError:
            continue
    return snapshot


def snapshot_digest(snapshot: Mapping[str, str]) -> str:
    return sha256_text(json.dumps(dict(sorted(snapshot.items())), ensure_ascii=False))


def _internal_load(args: Any) -> int:
    """内部入口：在**受监管子进程**里装载候选、构造调整、跑冷启动探针。

    **父进程绝不执行生成代码**：模块体、构造与 delta 全在这里；
    挂住时由父进程的墙钟上限与整组终止兜住（与门禁同一实现）。
    """

    code_path = Path(args.code)
    params = json.loads(args.params)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(code_path)
    payload: Dict[str, Any] = {
        "schema": LOAD_REPORT_SCHEMA,
        "code_sha256": digest,
        "code_path": str(code_path),
        "requested_params": params,
        "gate_level": "G-0 同级（受监管装载与构造）",
        "equivalent_to_three_gates": False,
        "gates_run": [],
        "ok": False,
        "reason": "",
        "sandbox": {
            "cwd": os.getcwd(),
            "env_keys": sorted(os.environ),
            "env_allowlisted": sorted(set(os.environ) & set(CHILD_ENV_ALLOWLIST)) or [],
            "pid": os.getpid(),
            "how": ("本进程就是隔离装载子进程：工作目录与父进程不同（mkdtemp），"
                    "环境变量来自白名单而不是整份 os.environ"),
        },
    }
    try:
        module_name = "sitin_generated_candidate_" + digest[:12]
        spec = importlib.util.spec_from_file_location(module_name, code_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        entry = getattr(module, ENTRY_NAME, None)
        if not callable(entry):
            raise ValueError("模块没有可调用的 {0}".format(ENTRY_NAME))
        # 与生产装载同口径：把**源码指纹**传进去，候选身份里才带 src 段
        # （policy/heuristics/__init__.py 的 build_candidate 就是这么传的）。
        # 少了它，"装载出来的身份"与"注册后门禁算出来的身份"会差一段。
        adjustments = {"default": entry({}, digest)}
        if params:
            adjustments["with_params"] = entry(dict(params), digest)
        construct: Dict[str, Any] = {}
        for label, adjustment in adjustments.items():
            spec_obj = adjustment.spec
            construct[label] = {
                "identity": adjustment.identity(),
                "spec": {"name": spec_obj.name, "version": spec_obj.version,
                         "thought": spec_obj.thought, "trigger": spec_obj.trigger,
                         "scope": list(spec_obj.scope), "bound": spec_obj.bound},
            }
        unknown_scope = [kind for kind in adjustments["default"].spec.scope
                         if kind not in ACTION_KINDS]
        if unknown_scope:
            raise ValueError("scope 含未知动作类别：{0}".format(unknown_scope))
        probe = cold_start_probe(adjustments["default"])
        synthetic = synthetic_facts_probe(adjustments["default"])
        payload["construct"] = construct
        # 两个探针**分开记录**：空事实探针只证明入口不炸（smoke_only），
        # 合成完整事实探针才把"读事实的分支"走到（mechanism_reachable）。GL-5
        payload["probe"] = probe
        payload["probe_synthetic_facts"] = synthetic
        payload["ok"] = bool(probe["ok"] and synthetic["ok"])
        problems: List[str] = []
        if not probe["ok"]:
            problems.append("空事实探针失败：{0}".format(
                [case.get("error") for case in probe["cases"] if case.get("error")]))
        if not synthetic["ok"]:
            problems.append("合成事实探针失败：{0}".format(
                [case.get("error") for case in synthetic["cases"] if case.get("error")]))
        payload["reason"] = "" if payload["ok"] else "；".join(problems)
    except Exception as exc:                              # noqa: BLE001 —— 装载失败即 FAIL
        payload["reason"] = "{0}: {1}".format(type(exc).__name__, exc)
    # 子进程把报告写进父进程给的临时目录，同样经 _write_json（内部即 WriteLedger），
    # 于是"所有写盘都经账本"这条结构约束没有例外。
    _write_json(out, payload)
    return 0


def supervised_load(code_path: Path, params: Mapping[str, float], *,
                    timeout_sec: Optional[float] = None,
                    registry_before: Optional[Mapping[str, str]] = None) -> LoadOutcome:
    """在**受监管子进程**里装载生成代码；父进程只做监管与读结果。

    加固措施（Lead 裁定 #9 —— 静态扫描是 lint，不是边界）：
      1. **子进程**执行（父进程绝不 exec 生成代码）；
      2. 子进程 cwd = mkdtemp()，不放它在仓库里跑；
      3. 子进程环境变量走**白名单**（child_env），不整份 os.environ 传下去；
      4. 装载**前后**对候选注册表目录取哈希快照，不一致即判失败
         ——"越界"因此是**查出来的**，不是假设的。

    为什么装载必须隔离：生成代码是**任意离线代码**，一个在模块体里挂住的候选
    会让调用方在被拒绝之前就挂死（REVIEW-8 S8-2 的同一条教训）。
    """

    import tempfile

    limit = float(timeout_sec) if timeout_sec is not None else LOAD_TIMEOUT_SEC
    workdir = Path(tempfile.mkdtemp(prefix="sitin-generate-load-"))
    out_path = workdir / "load.json"
    before = dict(registry_before) if registry_before is not None else registry_snapshot()
    command = [sys.executable, str(Path(__file__).resolve()), "--internal-load",
               "--code", str(code_path), "--params", json.dumps(dict(params)),
               "--out", str(out_path)]
    # 子进程 cwd 用临时目录、环境变量走白名单（不传整份 os.environ）、
    # 并且不让它写 __pycache__（证据目录里不该混进 .pyc）。
    try:
        # GL-4：临时目录**用完即删**（初版只在 finally 之外 mkdtemp，系统临时目录里
        # 累积了 765 个 sitin-generate-load-*）。
        result = process_guard.run_supervised(command, cwd=workdir, timeout_sec=limit,
                                              grace_sec=LOAD_TERM_GRACE_SEC,
                                              env=child_env())
        report_payload = (json.loads(out_path.read_text(encoding="utf-8"))
                          if out_path.is_file() else None)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    after = registry_snapshot()
    sandbox = {
        "child_cwd": str(workdir),
        "env_allowlist": list(CHILD_ENV_ALLOWLIST),
        "registry_files_before": len(before),
        "registry_digest_before": snapshot_digest(before),
        "registry_digest_after": snapshot_digest(after),
        "registry_unchanged": before == after,
        "how": ("子进程 + mkdtemp 工作目录 + 环境变量白名单；候选注册表目录在装载前后"
                "各取一次哈希快照，两次不一致即判失败"),
    }
    execution = result.to_json()
    execution["sandbox"] = sandbox
    if before != after:
        changed = sorted({name for name, _digest in (set(before.items()) ^ set(after.items()))})
        return LoadOutcome(False, "装载期间候选注册表目录发生变化（拒绝）：{0}".format(
            changed[:5]), None, execution)
    if result.timed_out:
        return LoadOutcome(False, "隔离装载超时：{0} 秒内未结束，已终止进程组（信号 {1}）".format(
            limit, "+".join(result.signals_sent) or "无"), None, execution)
    if result.returncode != 0 or report_payload is None:
        tail = result.stderr.strip().splitlines()[-1][:200] if result.stderr.strip() else ""
        return LoadOutcome(False, "隔离装载未产出结果：returncode={0}{1}".format(
            result.returncode, "；stderr 尾部：" + tail if tail else ""), None, execution)
    report = report_payload
    return LoadOutcome(bool(report.get("ok")), report.get("reason") or "", report, execution)


# ============================================================ 7. 调用台账（独立落盘、先预留后调用）

@dataclass
class GenerationBudget:
    """生成调用台账。

    **纪律**（与调度器台账同源）：① **先预留后调用**——预算不足就保存状态并停止，
    绝不允许"先调用再记账"；② 失败与重试**同样计费**；③ 台账独立落盘，
    不藏在日志里。
    """

    path: Path
    calls_budget: int
    max_total_tokens: int = DEFAULT_MAX_TOTAL_TOKENS
    spent_calls: int = 0
    spent_tokens: int = 0
    entries: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    #: 写盘账本（可选）：有它时，台账落盘也进"实际写出的路径"清单。
    writes: Optional["WriteLedger"] = None

    @property
    def remaining(self) -> int:
        return self.calls_budget - self.spent_calls

    def check_token_budget(self) -> None:
        """调模型**之前**检查累计 token 上限；已超限就停止并保存状态。"""

        if self.spent_tokens >= self.max_total_tokens:
            self.save()
            raise BudgetExhausted(
                "累计 token 已用尽（{0}/{1}）：保存状态并停止，不免费续跑".format(
                    self.spent_tokens, self.max_total_tokens))

    def charge_tokens(self, usage: Optional[Mapping[str, Any]]) -> int:
        """调用**之后**按实际 usage 记账；失败与重试同样计费。"""

        charged = usage_tokens(usage)
        self.spent_tokens += charged
        if self.entries:
            self.entries[-1]["tokens"] = charged
            self.entries[-1]["tokens_cumulative"] = self.spent_tokens
        self.save()
        return charged

    def reserve(self, note: str) -> Dict[str, Any]:
        """预留一次调用；不足则抛 `BudgetExhausted` 并**保存状态**。"""

        if self.remaining <= 0:
            self.save()
            raise BudgetExhausted(
                "调用预算已用尽（{0}/{1}）：保存状态并停止，不免费续跑".format(
                    self.spent_calls, self.calls_budget))
        self.spent_calls += 1
        entry = {"index": self.spent_calls, "note": note, "at_utc": utc_now(),
                 "status": "reserved"}
        self.entries.append(entry)
        self.save()
        return entry

    def settle(self, entry: Dict[str, Any], status: str, **fields: Any) -> None:
        entry.update({"status": status})
        entry.update(fields)
        self.save()

    def to_json(self) -> Dict[str, Any]:
        return {"schema": BUDGET_SCHEMA, "calls_budget": self.calls_budget,
                "spent_calls": self.spent_calls, "remaining_calls": self.remaining,
                "max_total_tokens": self.max_total_tokens,
                "spent_tokens": self.spent_tokens,
                "remaining_tokens": max(0, self.max_total_tokens - self.spent_tokens),
                "entries": list(self.entries)}

    def save(self) -> None:
        _write_json(self.path, self.to_json(), self.writes)

    @classmethod
    def load(cls, path: Path, calls_budget: Optional[int] = None,
             writes: Optional["WriteLedger"] = None,
             max_total_tokens: Optional[int] = None) -> "GenerationBudget":
        path = Path(path)
        tokens = int(max_total_tokens) if max_total_tokens is not None else DEFAULT_MAX_TOTAL_TOKENS
        if not path.is_file():
            if calls_budget is None:
                raise ValueError("台账不存在时必须给出 --calls-budget")
            return cls(path=path, calls_budget=int(calls_budget), writes=writes,
                       max_total_tokens=tokens)
        data = json.loads(path.read_text(encoding="utf-8"))
        budget = int(calls_budget) if calls_budget is not None else int(data["calls_budget"])
        if int(data["calls_budget"]) != budget:
            raise ValueError(
                "台账已存在且预算不同（记录 {0}，本次 {1}）：改预算请换 --out，"
                "不要就地改写台账".format(data["calls_budget"], budget))
        recorded_tokens = int(data.get("max_total_tokens", tokens))
        if max_total_tokens is not None and recorded_tokens != tokens:
            raise ValueError(
                "台账已存在且累计 token 上限不同（记录 {0}，本次 {1}）：改上限请换 --out".format(
                    recorded_tokens, tokens))
        return cls(path=path, calls_budget=budget, spent_calls=int(data.get("spent_calls", 0)),
                   entries=list(data.get("entries", [])), writes=writes,
                   max_total_tokens=recorded_tokens,
                   spent_tokens=int(data.get("spent_tokens", 0)))


class BudgetExhausted(RuntimeError):
    """调用预算用尽；**保存状态并停止**，不静默续跑。"""


# ============================================================ 8. 血缘：身份、父代绑定与落盘

#: 身份 → 目录名的字符替换表（与调度器 cell_dir_name 同一约定：
#: 可读 slug + 身份哈希后缀；后缀保证单射，slug 只负责可读）。
_DIR_NAME_TRANSLATION = str.maketrans({
    "|": "__", "(": "", ")": "", "=": "-", ",": "_",
    ":": "-", " ": "_", "/": "_", "\\": "_", "*": "_", "?": "_",
    "<": "_", ">": "_", '"': "_",
})


def attempt_dir_name(identity: str) -> str:
    """把血缘身份映射成**文件系统安全**的目录名。"""

    slug = identity.translate(_DIR_NAME_TRANSLATION)
    return "{0}-{1}".format(slug, hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8])


def attempt_identity(*, operator: str, contract_identity: str, prompt_sha: str,
                     parent_identity: Optional[str], code_sha: Optional[str],
                     reply_sha: str, origin: str, sampling_tag: str = "-",
                     ordinal: int = 1) -> str:
    """一次尝试的**完整身份**：算子 + 合同 + 提示词 + 父代 + 代码/回复 + 来源 + 采样 + 序号。

    **为什么必须带采样与序号**（第三阶段 Challenger #6）：一次真实调用如果被截断、
    正文为空，回复哈希就是**空串哈希**——两次**花了钱**的调用会得到同一个身份，
    后一次把前一次的目录整个覆盖，产物里就查不到第一次发生过什么。
    把采样参数与"本次运行内第几次尝试"纳入身份之后，同一份输入也能留下多条记录。

    四个后端产出的身份口径**完全一致**，因此换通道不会让目录与对账方式变化。
    """

    parent_tag = short(sha256_text(parent_identity)) if parent_identity else "-"
    return ("genloop|{op}|contract={c}|prompt={p}|parent={par}|code={code}"
            "|reply={r}|origin={o}|sampling={s}|attempt={n}").format(
        op=operator, c=short(contract_identity), p=short(prompt_sha),
        par=parent_tag, code=short(code_sha), r=short(reply_sha), o=origin,
        s=sampling_tag, n=int(ordinal))


def attempt_ordinal(out_dir: Path) -> int:
    """本次运行在该产物目录里的**第几次尝试**（按 records.jsonl 已有条数顺延）。"""

    path = Path(out_dir) / "records.jsonl"
    if not path.is_file():
        return 1
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    except OSError:
        return 1
    return len(lines) + 1


def sampling_tag_of(sampling: Optional[Mapping[str, Any]]) -> str:
    """采样参数的短标签；没有发生采样时是连字符（不是"默认采样"）。"""

    if not sampling:
        return "-"
    return short(sha256_text(json.dumps(dict(sampling), ensure_ascii=False,
                                        sort_keys=True)), 8)


def resolve_attempt_dir(out_dir: Path, *, operator: str, contract_identity: str,
                        prompt_sha: str, parent_identity: Optional[str],
                        code_sha: Optional[str], reply_sha: str, origin: str,
                        sampling: Optional[Mapping[str, Any]],
                        start_ordinal: int) -> Tuple[str, Path, int]:
    """定出本次尝试的身份与目录；**已存在且身份不同就顺延序号，绝不覆盖**。

    覆盖真实调用证据是不可接受的（花了钱的调用不能在产物里消失），
    因此这里既有"序号进身份"的预防，也有"撞上就顺延"的兜底。
    """

    tag = sampling_tag_of(sampling)
    ordinal = int(start_ordinal)
    while True:
        identity = attempt_identity(
            operator=operator, contract_identity=contract_identity, prompt_sha=prompt_sha,
            parent_identity=parent_identity, code_sha=code_sha, reply_sha=reply_sha,
            origin=origin, sampling_tag=tag, ordinal=ordinal)
        attempt_dir = Path(out_dir) / "attempts" / attempt_dir_name(identity)
        record_path = attempt_dir / "record.json"
        if not record_path.is_file():
            return identity, attempt_dir, ordinal
        try:
            existing = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:                                 # noqa: BLE001 —— 读不动就换序号
            existing = {}
        if existing.get("attempt_identity") == identity:
            return identity, attempt_dir, ordinal          # 同一次尝试重写：允许
        ordinal += 1


def parent_binding(parent_dir: Path) -> Dict[str, Any]:
    """核验父代：**按持久化产物重算**，而不是相信命令行（R8-3 的同一条纪律）。

    拒绝条件：记录 schema 不符、目录缺 candidate.py、代码哈希与记录不一致、
    父代自身解析或装载未通过。
    """

    parent_dir = Path(parent_dir)
    record_path = parent_dir / "record.json"
    if not record_path.is_file():
        raise ValueError("父代目录缺少 record.json：{0}".format(parent_dir))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != GENERATION_RECORD_SCHEMA:
        raise ValueError("父代记录 schema 不符：{0!r}".format(record.get("schema")))
    code_path = parent_dir / "candidate.py"
    if not code_path.is_file():
        raise ValueError("父代目录缺少 candidate.py：{0}".format(parent_dir))
    actual = sha256_file(code_path)
    recorded = (record.get("code") or {}).get("sha256")
    if actual != recorded:
        raise ValueError("父代代码与记录不一致：实际 {0}，记录 {1}".format(
            short(actual), short(recorded)))
    if (record.get("parse") or {}).get("status") != PARSE_OK:
        raise ValueError("父代解析未通过（没有可用的 thought/code），不能作为修订基础")
    # **装载失败的候选仍可作父代**：PLAN §3.2 要求"拒绝诊断 → 后续修订请求"，
    # 那正是修复路径的入口。父代的装载状态如实带进血缘，不在这里替它遮掩。
    return {
        "dir": str(parent_dir),
        "identity": record["attempt_identity"],
        "code_sha256": actual,
        "record_sha256": sha256_file(record_path),
        "operator": record.get("operator"),
        "thought": (record.get("parse") or {}).get("thought") or "",
        "code": code_path.read_text(encoding="utf-8"),
        "load_ok": bool((record.get("load") or {}).get("ok")),
        "repair_depth": int((record.get("lineage") or {}).get("repair_depth", 0)),
        "verified": True,
    }


def feedback_from_diagnosis(record: Mapping[str, Any]) -> str:
    """把**拒绝诊断**整理成三段反馈（PLAN §3.2：事实 / 相关表现 / 机制假设分开）。

    只有"事实"段有内容：解析状态、静态扫描问题、隔离装载结论都是本工具**实测**的；
    相关表现段本轮为空（没有跑桌赛），机制假设段留给人填。
    """

    parse = record.get("parse") or {}
    scan = (record.get("code") or {}).get("scan") or {}
    load = record.get("load") or {}
    lines = [
        "【事实】上一次生成被本工具拒绝，诊断如下（均为工具实测，不是模型判断）：",
        "  - 解析状态：{0}".format(parse.get("status")),
        "  - 解析问题：{0}".format("；".join(parse.get("problems") or []) or "无"),
        "  - 静态扫描问题：{0}".format("；".join(scan.get("problems") or []) or "无"),
        "  - 隔离装载：ok={0}；原因：{1}".format(load.get("ok"), load.get("reason") or "无"),
        "【相关表现】（本轮为空：未跑桌赛，没有开发集表现）",
        "【机制假设】（留空，由人填写）",
        "请只做**有界修订**：修掉上面被拒绝的原因，不得改动函数合同、允许面与硬限制。",
    ]
    return "\n".join(lines)


def _guard_secrets(payload: Any, secrets: Sequence[str]) -> List[str]:
    """落盘前的凭据复核；发现即抛错（**不写出**）。"""

    leaks = find_leaked_secrets(payload, secrets)
    if leaks:
        raise ValueError("检出凭据明文（指纹 {0}）：拒绝写出任何产物".format(leaks))
    return leaks


# ============================================================ 9. 编排：emit / ingest

@dataclass(frozen=True)
class AttemptContext:
    """一次尝试的输入快照；emit 与 ingest 用它保持**同一份提示词**。

    提示词由（合同, 算子, 父代, 反馈）**确定性**生成，因此 ingest 时重算即可对上哈希，
    不需要把提示词文本在两次调用之间传来传去（少一个可漂移的中间态）。
    """

    operator: str
    packet: PromptPacket
    contract: TaskContract


def prepare_attempt(operator: str, contract: TaskContract, parent: Optional[Mapping[str, Any]],
                    feedback: str) -> AttemptContext:
    """构造提示词；M1 缺父代直接报错（不退回 I1，避免"看起来修订了其实没有"）。"""

    if operator == OPERATOR_I1:
        packet = build_i1_prompt(contract)
    elif operator == OPERATOR_M1:
        if not parent:
            raise ValueError("M1 必须有父代；请给 --parent <父代目录>")
        packet = build_m1_prompt(contract, parent["thought"], parent["code"], feedback,
                                 parent_identity=parent["identity"])
    else:
        raise ValueError("未知算子：{0!r}".format(operator))
    return AttemptContext(operator=operator, packet=packet, contract=contract)


def emit_prompt(context: AttemptContext, out_dir: Path, *, backend: str,
                parent_dir: Optional[Path] = None,
                writes: Optional[WriteLedger] = None) -> Dict[str, Any]:
    """文件式交接：写提示词原文、哈希与允许面清单（**不发任何请求、不产出候选**）。"""

    writes = writes or WriteLedger(out_dir)
    pending = Path(out_dir) / "pending" / context.operator
    # **交接文件与被哈希的文本逐字节一致**：不额外补换行。
    # 否则下游（委派方）按文件算 sha256 会与 prompt_sha256 对不上——
    # 委派通道的实际操作者已经踩到过这一点，必须让"文件哈希 = 提示词哈希"可自证。
    writes.write_text(pending / "prompt.txt", context.packet.text)
    contract_payload = context.contract.to_json()
    writes.write_json(pending / "prompt.json", {
        "schema": "sitin-generation-prompt/1",
        "operator": context.operator,
        "backend": backend,
        "prompt_sha256": context.packet.sha256,
        "prompt_path": "prompt.txt",
        "prompt_chars": len(context.packet.text),
        "contract_identity": context.packet.contract_identity,
        "parent_identity": context.packet.parent_identity,
        "feedback_sha256": context.packet.feedback_sha256,
        "allowed_surface": contract_payload["facts"],
        "limits": contract_payload["limits"],
        "counterexamples": contract_payload["counterexamples"],
        "forbidden": contract_payload["forbidden"],
    })
    writes.write_json(pending / "delegation-request.json", {
        "schema": "sitin-generation-delegation/1",
        "operator": context.operator,
        "parent_dir": str(parent_dir) if parent_dir else None,
        "prompt_sha256": context.packet.sha256,
        "how_to_use": [
            "1) 把 prompt.txt 的**原文**交给生成方，不要改写提示词。",
            "2) 把回复原文逐字写进一个 JSON 文件，字段如下（schema/origin 两个键必须照写）：",
            "   schema=sitin-generation-reply/1",
            "   origin=delegated_model_reply",
            "   prompt_sha256=<本文件里的 prompt_sha256>",
            "   reply=<回复原文>",
            "   provider=<生成方提供方>；model=<生成方模型标识>；captured_at_utc=<墙钟时间>；",
            "   delegator=<发起委派的人或会话>",
            "3) 回到本工具：i1/m1 --backend delegate --ingest-reply <该 JSON> 走完解析与装载。",
            "工具**不会**也不该自己调用外部代理：委派由人/上游执行，工具只做交接与摄入。",
        ],
        "reply_file_template": {
            "schema": REPLY_FILE_SCHEMA, "origin": ORIGIN_DELEGATED,
            "prompt_sha256": context.packet.sha256, "reply": "<回复原文>",
            "provider": "<提供方>", "model": "<模型标识>",
            "captured_at_utc": "<UTC 墙钟时间>", "delegator": "<发起委派的人或会话>",
        },
    })
    return {"prompt_dir": str(pending), "prompt_sha256": context.packet.sha256,
            "writes": writes.to_json()}


def ingest_reply(*, context: AttemptContext, out_dir: Path, backend: str,
                 env: Mapping[str, Any], parent: Optional[Mapping[str, Any]],
                 ledger: GenerationBudget, params: Mapping[str, float],
                 load_timeout_sec: Optional[float], secrets: Sequence[str],
                 started_monotonic: float,
                 writes: Optional[WriteLedger] = None) -> Dict[str, Any]:
    """摄入回复并走完 解析 → 静态扫描 → 隔离装载 → 血缘落盘。

    每一步失败都会**照常落盘**：失败记录也是证据（尤其"模型产出的格式不合格"这件事
    只有留下原文才能复核），只是 `load.ok` 与 `admission.eligible` 恒为假。
    """

    reply: ModelReply = env["reply"]
    out_dir = Path(out_dir)
    writes = writes or WriteLedger(out_dir)
    reply_sha = sha256_text(reply.text)
    # 装载**之前**取注册表快照：准入里的 registered 用这一份（Lead 裁定 #9）。
    registry_before = registry_snapshot()
    parsed = parse_model_reply(reply.text)
    if reply.finish_reason not in (None, "stop"):
        # finish_reason != stop ⇒ **回复被截断**。推理型模型的典型形态是"正文为空、
        # 只有思维链"，此时就算正则能抠出半段代码也**不得当合法回复解析**：
        # 半截代码进装载只会得到误导性的失败。只保留原文供复核，并按"回复不合法"
        # 进修复路径（m1 --from-diagnosis）。
        parsed = ParsedReply(
            PARSE_TRUNCATED, None, None,
            ("finish_reason={0}：回复被截断（推理模型常见：正文为空、只有思维链），"
             "不得当合法回复解析；已丢弃该回复的部分提取结果".format(reply.finish_reason),)
            + parsed.problems)
    # 落盘代码 = 被哈希的代码：统一走 normalized_code()（见该函数 docstring）。
    code_text = normalized_code(parsed.code) if parsed.code else None
    code_sha = sha256_text(code_text) if code_text else None
    identity, attempt_dir, ordinal = resolve_attempt_dir(
        out_dir, operator=context.operator, contract_identity=context.contract.identity(),
        prompt_sha=context.packet.sha256, parent_identity=context.packet.parent_identity,
        code_sha=code_sha, reply_sha=reply_sha, origin=reply.origin,
        sampling=env.get("sampling"), start_ordinal=attempt_ordinal(out_dir))
    attempt_dir.mkdir(parents=True, exist_ok=True)
    # 记录与汇总里的 attempt_dir 统一用**相对 out_dir 的路径**，
    # 免得两处口径不同（一处是裸目录名、一处是相对路径，读的人各按各的理解拼接）。
    attempt_rel = str(attempt_dir.relative_to(out_dir))

    # 同 emit_prompt：落盘的提示词原文与 prompt_sha256 逐字节一致（不加换行）。
    writes.write_text(attempt_dir / "prompt.txt", context.packet.text)
    sent_prompt = env.get("prompt_sent")
    sent_meta: Dict[str, Any] = {}
    if sent_prompt and sent_prompt != context.packet.text:
        # 通道后缀（例如 headless 的"不要使用任何工具"）改变了**实际发出**的提示词：
        # 把实际发出的那一份也落盘并单独记哈希，而不是只记"合同提示词"。
        writes.write_text(attempt_dir / "prompt_sent.txt", sent_prompt)
        sent_meta = {"sent_path": "prompt_sent.txt", "sent_sha256": sha256_text(sent_prompt),
                     "sent_chars": len(sent_prompt),
                     "channel_suffix_chars": len(sent_prompt) - len(context.packet.text)}
    writes.write_json(attempt_dir / "prompt.json", {
        "schema": "sitin-generation-prompt/1",
        "path": "prompt.txt",
        "allowed_surface": context.contract.to_json()["facts"],
        **context.packet.to_json(),
        **sent_meta,
    })
    writes.write_text(attempt_dir / "reply_raw.txt", reply.text)
    writes.write_json(attempt_dir / "parsed.json", parsed.to_json())

    scan_json: Optional[Dict[str, Any]] = None
    load_json: Dict[str, Any] = {
        "ok": False, "reason": "解析未通过，未进入隔离装载",
        "gate_level": "G-0 同级（受监管装载与构造）",
        "equivalent_to_three_gates": False, "gates_run": [],
    }
    if parsed.ok and code_text:
        writes.write_text(attempt_dir / "candidate.py", code_text)
        scan = scan_generated_code(code_text)
        scan_json = scan.to_json()
        writes.write_json(attempt_dir / "scan.json", scan_json)
        if scan.ok:
            load_json = supervised_load(attempt_dir / "candidate.py", params,
                                        timeout_sec=load_timeout_sec,
                                        registry_before=registry_before).to_json()
        else:
            load_json = {
                "ok": False, "reason": "静态扫描未通过，未进入隔离装载",
                "gate_level": "G-0 同级（受监管装载与构造）",
                "equivalent_to_three_gates": False, "gates_run": [],
            }
    writes.write_json(attempt_dir / "load.json", load_json)

    # 准入状态**实际去查**：注册表目录里有没有同一份源码、门禁记录有没有指向它。
    # registered 取**装载前**快照（装载期间的写入由 supervised_load 的快照比对单独判失败）。
    registered, gate_hits = probe_registry_source(code_sha, registry_before)
    as_of = utc_now()
    record: Dict[str, Any] = {
        "schema": GENERATION_RECORD_SCHEMA,
        "attempt_identity": identity,
        "attempt_ordinal": ordinal,
        "attempt_dir": attempt_rel,
        "operator": context.operator,
        "backend": backend,
        "created_at_utc": as_of,

        "task": context.contract.to_json(),
        "prompt": {**context.packet.to_json(), "path": "prompt.txt", **sent_meta},
        "model": {
            "provider": reply.provider, "model": reply.model,
            # **模型身份冻结**：请求声明的模型、响应回显的模型、端点主机与凭据来源
            # （来源是"哪来的"，不是密钥本身）。非 api 通道这些字段为 None——
            # 那时它们确实不可知，写成猜测值才是造假。
            "model_requested": env.get("model_requested") or reply.model_requested,
            "endpoint_host": env.get("endpoint_host") or reply.endpoint_host,
            "tier": env.get("tier"),
            "credential_source": env.get("credential_source"),
            # headless：身份来自**运行痕迹**（会话文件里的 request/header.config），
            # 比"请求里声明了什么"更硬；观测不到就为 null，不写"应该是"。
            "observed_config": env.get("observed_config"),
            # 用量来源：api = response_body；headless = session_log（会话日志累加）
            "usage_source": reply.usage_source,
            "identity_source": ("session_log" if env.get("observed_config")
                                else ("response_echo" if backend == BACKEND_API else None)),
            "captured_at_utc": reply.captured_at_utc, "delegator": reply.delegator,
            # 采样只在**真的发出过请求**时才有值：delegate/replay 通道没有发生采样，
            # 写一组"看起来像采样设置"的数字会让读的人以为请求带过这些参数（Challenger #14）。
            "sampling": env.get("sampling"),
            "request_identity": dict(env.get("request_identity") or {}),
        },
        "parent": ({"identity": parent["identity"], "dir": parent["dir"],
                    "code_sha256": parent["code_sha256"],
                    "record_sha256": parent["record_sha256"],
                    # 父代若自身装载失败，这里如实写着 False——它是"修复型修订"，
                    # 不是"在好父代上继续变强"（两者结论强度不同）。
                    "load_ok": parent.get("load_ok"), "verified": True}
                   if parent else None),
        "lineage": {
            "operator": context.operator,
            "parent_identity": context.packet.parent_identity,
            "repair_depth": (int(parent["repair_depth"]) + 1) if parent else 0,
            "feedback_sha256": context.packet.feedback_sha256,
        },
        "reply": {
            **reply.to_json(),
            "path": "reply_raw.txt",
            "raw_sha256": reply_sha,
            "backend_file": env.get("reply_file"),
        },
        "parse": parsed.to_json(),
        # **GL-1**：只有真的把 candidate.py 写出来了，才给 code 段。
        # 初版无条件按 code_sha 给出，于是解析失败的记录里 code.sha256 指向一个
        # **不存在的文件**——读的人会以为代码落盘了。
        "code": ({"path": "candidate.py", "stored": True, "sha256": code_sha,
                  "params": dict(params), "scan": scan_json}
                 if (parsed.ok and code_text) else
                 {"stored": False, "sha256": None,
                  "reason": "解析未通过，未落盘候选代码（原文见 reply_raw.txt）"}),
        "load": load_json,
        # registered / wrote_to_src 在落盘后由**实际检查**回填（见函数尾部）。
        "registration": {"registered": registered, "auto_publish": False,
                         "requires_human_review": True, "wrote_to_src": None,
                         "note": ("静态注册与人工发布合同不变；本工具没有自动上线通道，"
                                  "也不会自己解冻——解冻路径见 admission.unfreeze_path")},
        "admission": admission_block(code_sha256=code_sha, registered=registered,
                                     gate_hits=gate_hits, as_of=as_of),
        "gates_run": [],
        "budget": {"calls_budget": ledger.calls_budget, "spent_calls": ledger.spent_calls,
                   "remaining_calls": ledger.remaining,
                   # 累计 token：本次调用消耗 + 台账累计（超限即停止，见 budget.json）
                   "call_tokens": usage_tokens(reply.usage),
                   "spent_tokens": ledger.spent_tokens,
                   "max_total_tokens": ledger.max_total_tokens},
        "timings": {"wall_time_utc": as_of,
                    "monotonic_elapsed_sec": round(time.monotonic() - started_monotonic, 3),
                    # 通道自身的调用耗时：headless 每次起一个 DSH 进程，明显高于直连 HTTP
                    "backend_elapsed_sec": env.get("backend_elapsed_sec")},
        # 信息边界只在**工具自己发出过请求**时才谈得上：
        #   headless = weak（运行体具备工作区能力，只能靠提示词约束）；
        #   api      = strong（无工具、无文件访问能力）；
        #   delegate/replay/夹具 = **n/a**（工具没有发出任何请求，回复来自落盘文件／人工夹具）。
        # 初版把所有非 headless 都写成 strong + "api 直连"的解释，于是 delegate 与夹具记录里
        # 出现"无工具、无文件访问能力"这种**与事实不符**的表述（那一条根本不是直连），
        # 而且与同一条记录的 provenance_attestation=envelope-self-declared 自相矛盾。
        "info_boundary": info_boundary_block(env.get("info_boundary"), backend),
        "redactions": {"secrets_checked": len(secrets), "leaks_found": []},
    }
    leaks = _guard_secrets(record, secrets)
    record["redactions"]["leaks_found"] = leaks
    writes.write_json(attempt_dir / "record.json", record)
    summary_row = {
        "schema": GENERATION_RECORD_SCHEMA,
        "attempt_identity": identity,
        "attempt_dir": attempt_rel,
        "operator": context.operator,
        "backend": backend,
        "evidence_kind": reply.evidence_kind,
        "is_model_output": reply.to_json()["is_model_output"],
        "parse_status": parsed.status,
        "load_ok": bool(load_json.get("ok")),
        "admission_eligible": False,
        "created_at_utc": record["created_at_utc"],
    }
    writes.append_text(out_dir / "records.jsonl",
                       json.dumps(summary_row, ensure_ascii=False) + "\n")
    # 汇总也在快照之前写：这样 record["writes"] 覆盖本次运行的**全部**产物形态
    # （attempts/**、records.jsonl、budget.json、summary.md 与本记录自身）——
    # Challenger #13 要的正是"这条回归得真的证明它宣称的东西"。
    write_summary(out_dir, writes)
    writes.record(attempt_dir / "record.json")      # 本记录自身（下面这条语句写它）
    # 写盘账本在**所有产物落地之后**取快照，再回填进记录——于是 wrote_to_src /
    # all_under_out 是**查出来的**，不是断言出来的（Challenger #11/#13）。
    writes_block = writes.to_json()
    record["writes"] = writes_block
    record["registration"]["wrote_to_src"] = writes_block["src_touched"]
    writes.write_json(attempt_dir / "record.json", record)
    return record


def write_summary(out_dir: Path, writes: Optional[WriteLedger] = None) -> str:
    """把 records.jsonl 汇总成一页人读表格；**口径与记录一致，不新增结论**。"""

    out_dir = Path(out_dir)
    lines = ["# 坐隐 3.1 生成闭环：尝试汇总", "",
             "**边界**：装载通过只是 G-0 同级结论；三条硬边界（未注册 / 未准入 / 无自动上线）",
             "已写进每条记录，汇总不改变它们。", "",
             "| 尝试 | 算子 | 后端 | 来源 | 是模型输出 | 解析 | 装载 | 准入 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    rows: List[Dict[str, Any]] = []
    path = out_dir / "records.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    for row in rows:
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
            str(row["attempt_identity"]).replace("|", "\\|"), row["operator"], row["backend"],
            row["evidence_kind"], "是" if row["is_model_output"] else "否(夹具)",
            row["parse_status"], "PASS" if row["load_ok"] else "FAIL",
            "eligible" if row["admission_eligible"] else "pending_admission"))
    lines.append("")
    lines.append("共 {0} 次尝试。".format(len(rows)))
    text = "\n".join(lines) + "\n"
    writes = writes or WriteLedger(out_dir)
    writes.write_text(out_dir / "summary.md", text)
    return text


# ============================================================ 10. 命令行

def _sampling_from_args(args: Any) -> SamplingSpec:
    return SamplingSpec(temperature=args.temperature, top_p=args.top_p,
                        max_tokens=args.max_tokens, seed=args.seed)


def sampling_record(backend: str, spec: SamplingSpec, *, sent: bool) -> Optional[Dict[str, Any]]:
    """采样记录：**只有真的发出过请求**才记录，并注明参数来源。

    delegate/replay 通道不发生采样：此时写一组采样值会让人以为"请求带过这些参数"
    （第三阶段 Challenger #14）。只有 api 后端把参数放进请求体，才记录实际生效值，
    并写明 `values` 来自请求体、`values_origin` 是命令行或默认值。
    """

    if not sent:
        return None
    return {
        "values": spec.to_request_fields(),
        "omitted": spec.omitted_fields(),
        "source": "request_body",
        "values_origin": "cli_args_or_defaults",
        "sent_backend": backend,
    }


def _load_feedback(args: Any) -> str:
    """反馈来源二选一：显式文件，或**上一次尝试的拒绝诊断**（都不是就不给反馈）。"""

    if args.feedback and args.from_diagnosis:
        raise ValueError("--feedback 与 --from-diagnosis 只能给一个")
    if args.feedback:
        return Path(args.feedback).read_text(encoding="utf-8")
    if args.from_diagnosis:
        record_path = Path(args.from_diagnosis) / "record.json"
        if not record_path.is_file():
            raise ValueError("--from-diagnosis 目录缺少 record.json：{0}".format(
                args.from_diagnosis))
        return feedback_from_diagnosis(
            json.loads(record_path.read_text(encoding="utf-8")))
    return ""


def _run_generate(args: Any, operator: str) -> int:
    # 候选种类分流（D 包）：action_value_v1 走新路径；缺省保持旧 delta 原义。
    if getattr(args, "candidate_kind", "delta") == "action_value_v1":
        return _run_generate_action_value(args, operator)
    # 守卫在**建目录之前**：越界的 --out 必须在写第一个字节之前就失败。
    out_dir = guard_out_dir(Path(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)
    writes = WriteLedger(out_dir)
    started = time.monotonic()
    contract = default_task_contract()
    parent: Optional[Dict[str, Any]] = None
    if args.parent:
        parent = parent_binding(Path(args.parent))
        depth_limit = int(args.repair_depth)
        if parent["repair_depth"] + 1 > depth_limit:
            raise ValueError(
                "血缘修复深度超限：父代深度 {0}，上限 {1}（失败修复受调用上限限制）".format(
                    parent["repair_depth"], depth_limit))
    feedback = _load_feedback(args)
    context = prepare_attempt(operator, contract, parent, feedback)
    params = json.loads(args.params)
    backend_kind = BACKEND_REPLAY if args.replay else args.backend

    if args.dry_run:
        print(context.packet.text)
        print("\n--- prompt_sha256: {0}".format(context.packet.sha256), file=sys.stderr)
        return 0
    if args.emit_prompt:
        info = emit_prompt(context, out_dir, backend=backend_kind,
                           parent_dir=Path(args.parent) if args.parent else None,
                           writes=writes)
        info["operator"] = operator
        info["contract_identity"] = context.packet.contract_identity
        info["parent_identity"] = context.packet.parent_identity
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    ledger = GenerationBudget.load(out_dir / "budget.json", calls_budget=args.calls_budget,
                                   writes=writes, max_total_tokens=args.max_total_tokens)
    secrets = collect_secrets()
    ledger.check_token_budget()          # 累计 token 超限就地停止并保存状态
    entry = ledger.reserve("{0}/{1}".format(operator, backend_kind))
    try:
        reply_file = args.replay or args.reply_file
        # 只管"实际发出的提示词"：文件式通道没有额外后缀，保持 None（与合同提示词一致）。
        sent_prompt: Optional[str] = None
        if args.ingest_reply:
            if args.backend not in (BACKEND_DELEGATE, BACKEND_REPLAY):
                raise TransportError(
                    "--ingest-reply 只用于 delegate/replay 后端；api 后端请直接调用")
            data = load_reply_envelope(Path(args.ingest_reply),
                                       prompt_sha256=context.packet.sha256)
            reply = ModelReply(
                text=data["reply"], backend=args.backend, origin=data["origin"],
                provider=data.get("provider"), model=data.get("model"),
                captured_at_utc=data.get("captured_at_utc"),
                usage=data.get("usage") or {}, finish_reason=data.get("finish_reason"),
                note=data.get("note"), delegator=data.get("delegator"))
            backend_path = str(args.ingest_reply)
        else:
            if backend_kind == BACKEND_DELEGATE:
                raise TransportError(
                    "delegate 后端不与模型直接通信：先 --emit-prompt 交接，"
                    "拿到回复后再 --ingest-reply <文件>（见 pending/*/delegation-request.json）")
            backend = build_backend(
                backend_kind, prompt_sha256=context.packet.sha256,
                reply_file=Path(reply_file) if reply_file else None,
                base_url=args.base_url, model=args.model,
                config=Path(args.config) if args.config else None,
                api_key_env=args.api_key_env, sampling=_sampling_from_args(args),
                timeout_sec=(args.headless_timeout_sec
                             if backend_kind == BACKEND_HEADLESS
                             else args.request_timeout_sec),
                endpoint=getattr(args, "endpoint", None), tier=getattr(args, "tier", None),
                dsh_bin=getattr(args, "dsh_bin", "dsh"),
                dsh_home=(Path(args.dsh_home) if getattr(args, "dsh_home", None) else None))
            # GL-2：**解析出来的密钥也要进遮蔽集合**（初版只查环境变量与默认私有路径，
            # --config 指定的那份密钥漏在外面），并且写盘账本对每个文本产物都复核。
            secrets = collect_secrets(getattr(backend, "_api_key", None))
            writes.secrets = tuple(secrets)
            reply = backend.complete(context.packet.text)
            backend_path = str(reply_file) if reply_file else None
            sent_prompt = getattr(backend, "prompt_sent", None)
            api_identity = {
                "endpoint_host": getattr(backend, "endpoint_host", None),
                "credential_source": getattr(backend, "credential_source", None),
                "tier": getattr(backend, "tier", None),
            }
        # **调用后按实际 usage 记账**（失败与重试同样计费；超限由 check_token_budget 拦住）。
        if not args.ingest_reply:
            charged = ledger.charge_tokens(reply.usage)
            if charged == 0:
                # **确实没有用量**时（日志里没有 usage 事件、或通道不报用量）才标 unknown；
                # headless 的用量来自会话日志并已累加，正常不会再走到这里。
                ledger.entries[-1]["tokens_unknown"] = True
                ledger.save()
        # 采样：**只有 api 直连**把 CLI 的采样参数放进请求体。headless 的采样由 DSH profile
        # 决定（观测值在 model.observed_config），CLI 的 --temperature/--max-tokens 对它无效，
        # 不能照抄进 sampling —— 那会把"没发过的参数"写成"实际生效的参数"。
        request_sent = backend_kind == BACKEND_API and not args.ingest_reply
        sampling = sampling_record(backend_kind, _sampling_from_args(args), sent=request_sent)
        if backend_kind == BACKEND_HEADLESS and not args.ingest_reply:
            sampling = {
                "values": None,
                "source": "channel_defaults",
                "note": ("headless 的采样由 DSH profile 决定（观测值见 model.observed_config）；"
                         "CLI 的采样开关对该通道无效"),
                "cli_flags_ignored": _sampling_from_args(args).to_json(),
            }
            if args.temperature is not None and args.temperature != DEFAULT_TEMPERATURE:
                print("警告：--temperature 对 headless 通道无效（采样由 DSH profile 决定）",
                      file=sys.stderr)
        if args.ingest_reply:
            # 文件式摄入：工具侧没有发出任何请求，端点与凭据来源确实不可知。
            api_identity = {"endpoint_host": None, "credential_source": None, "tier": None}
        # 注意：headless 也要保留 credential_source（密钥被注入过子进程，来源是可知的），
        # 初版用 "not request_sent" 当条件，把 headless 的来源一起抹成了 None。
        env = {"reply": reply, "reply_file": backend_path,
               "sampling": sampling,
               "endpoint_host": api_identity["endpoint_host"] or reply.endpoint_host,
               "credential_source": api_identity["credential_source"],
               "tier": api_identity["tier"],
               "model_requested": args.model if request_sent else None,
               # headless：**实际发出的提示词**（含通道后缀）与本次运行写出的会话文件
               "prompt_sent": sent_prompt,
               "session_file": reply.session_file,
               "observed_config": dict(reply.observed_config) if reply.observed_config else None,
               "backend_elapsed_sec": reply.elapsed_sec,
               "info_boundary": reply.info_boundary,
               "request_identity": {"backend": backend_kind,
                                    "endpoint": args.base_url if request_sent
                                    and backend_kind == BACKEND_API else None,
                                    "model_arg": args.model if request_sent else None,
                                    "dsh_home": (str(args.dsh_home) if backend_kind
                                                 == BACKEND_HEADLESS else None)}}
        record = ingest_reply(context=context, out_dir=out_dir, backend=backend_kind,
                              env=env, parent=parent, ledger=ledger, params=params,
                              load_timeout_sec=args.load_timeout_sec, secrets=secrets,
                              started_monotonic=started, writes=writes)
        ledger.settle(entry, "completed", attempt_identity=record["attempt_identity"],
                      parse_status=record["parse"]["status"],
                      load_ok=record["load"]["ok"])
        write_summary(out_dir, writes)
        print(json.dumps({
            "attempt_identity": record["attempt_identity"],
            "attempt_dir": record["attempt_dir"],
            "evidence_kind": record["reply"]["evidence_kind"],
            "parse_status": record["parse"]["status"],
            "load_ok": record["load"]["ok"],
            "load_reason": record["load"].get("reason") or "",
            "admission": record["admission"]["status"],
            "writes_all_under_out": record["writes"]["all_under_out"],
            "writes_src_touched": record["writes"]["src_touched"],
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:                              # noqa: BLE001 —— 失败也要记账
        ledger.settle(entry, "failed", error="{0}: {1}".format(type(exc).__name__, exc))
        write_summary(out_dir, writes)
        raise


def _run_load(args: Any) -> int:
    out_dir = guard_out_dir(Path(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)
    writes = WriteLedger(out_dir)
    outcome = supervised_load(Path(args.code), json.loads(args.params),
                              timeout_sec=args.load_timeout_sec)
    payload = outcome.to_json()
    writes.write_json(out_dir / "load-report.json", payload)
    payload["writes"] = writes.to_json()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if outcome.ok else 2


def _run_surface(args: Any) -> int:
    contract = default_task_contract()
    payload = {"schema": CONTRACT_SCHEMA, "check": check_surface(),
               "contract_identity": contract.identity(),
               "contract": contract.to_json(),
               "prompt_sha256": {OPERATOR_I1: build_i1_prompt(contract).sha256}}
    if args.out:
        out_dir = guard_out_dir(Path(args.out))
        out_dir.mkdir(parents=True, exist_ok=True)
        writes = WriteLedger(out_dir)
        writes.write_json(out_dir / "allowed-surface.json", payload)
        payload["writes"] = writes.to_json()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["check"]["ok"] else 2


def _run_budget(args: Any) -> int:
    ledger = GenerationBudget.load(Path(args.out) / "budget.json",
                                   calls_budget=args.calls_budget)
    print(json.dumps(ledger.to_json(), ensure_ascii=False, indent=2))
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", required=True, help="产物目录（本工具只写这里）")
    parser.add_argument("--backend", choices=BACKENDS, default=BACKEND_HEADLESS,
                        help=("模型调用后端；**默认 headless**（受隔离约束的 DSH 子进程），"
                              "另有 api（直连 HTTP）/ delegate（文件式委派）/ replay（回放）"))
    parser.add_argument("--replay", default=None, help="回放后端：落盘回复文件")
    parser.add_argument("--reply-file", default=None, help="--replay 的别名")
    parser.add_argument("--ingest-reply", default=None,
                        help="摄入回复文件（delegate/replay 后端完成闭环）")
    parser.add_argument("--emit-prompt", action="store_true",
                        help="只产出提示词交接件，不发请求、不记账")
    parser.add_argument("--dry-run", action="store_true",
                        help="把提示词打到标准输出，不写产物、不发请求")
    parser.add_argument("--params", default="{}", help="候选声明参数 JSON（adj.* 去掉前缀）")
    parser.add_argument("--calls-budget", type=int, default=DEFAULT_CALLS_BUDGET,
                        help="调用预算（次）；**先预留后调用**，失败与重试同样计费")
    parser.add_argument("--max-total-tokens", type=int, default=None,
                        help=("调用 token 的累计上限（缺省 {0}）：超限停止并在台账里记账；"
                              "默认输出上限是 {1}，该端点合法区间 [1, 393216]").format(
                                  DEFAULT_MAX_TOTAL_TOKENS, DEFAULT_MAX_TOKENS))
    parser.add_argument("--load-timeout-sec", type=float, default=None,
                        help="隔离装载墙钟上限（秒）")
    parser.add_argument("--base-url", default=None, help="api 后端：OpenAI 兼容 base_url")
    parser.add_argument("--model", default=None, help="api 后端：模型标识")
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV,
                        help="api 后端：凭据环境变量名（凭据不落盘）")
    parser.add_argument("--config", default=None,
                        help="api 后端：私有配置 JSON 路径（优先于环境变量与默认路径）")
    parser.add_argument("--endpoint", default=None,
                        help="api 后端：私有配置里的端点名（默认取文件的 default_endpoint）")
    parser.add_argument("--tier", default=None, choices=("junior", "senior"),
                        help=("api 后端：按私有配置的 models 映射选模型（与 --model 二选一）；"
                              "缺省 {0}（用户裁定本轮用 deepseek-flash）".format(DEFAULT_TIER)))
    parser.add_argument("--request-timeout-sec", type=float,
                        default=DEFAULT_REQUEST_TIMEOUT_SEC)
    parser.add_argument("--dsh-bin", default="dsh", help="headless 通道：dsh 可执行文件")
    parser.add_argument("--dsh-home", default=None,
                        help="headless 通道：DSH_HOME（缺省 <仓库>/.dsh-headless，已在 .gitignore）")
    parser.add_argument("--headless-timeout-sec", type=float,
                        default=DEFAULT_HEADLESS_TIMEOUT_SEC,
                        help="headless 通道：单次调用墙钟上限（秒）；每次要起一个 DSH 进程")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=DEFAULT_TOP_P)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--parent", default=None,
                        help="父代目录（含 record.json 与 candidate.py）；M1 必填")
    parser.add_argument("--feedback", default=None, help="反馈文本文件")
    parser.add_argument("--from-diagnosis", default=None,
                        help="用上一次尝试的拒绝诊断构造反馈（目录含 record.json）")
    parser.add_argument("--repair-depth", type=int, default=DEFAULT_REPAIR_DEPTH,
                        help="血缘修复深度上限（默认 {0}）：失败修复受调用上限限制".format(
                            DEFAULT_REPAIR_DEPTH))
    parser.add_argument("--candidate-kind", choices=("delta", "action_value_v1"),
                        default="delta",
                        help="候选种类分流：action_value_v1 走 §10 机器合同渲染的新路径；"
                             "缺省 delta 走旧评分调整生成路径（原义不变）")
    parser.add_argument("--llm-authorization", default=None,
                        help="真实 LLM 通道（api/headless）的授权 JSON（authorized=true）；"
                             "缺省时 action_value_v1 对真实调用 fail-closed，不读私有凭据")
    parser.add_argument("--objective", default=None,
                        help="action_value_v1：本批目标摘要（缺省读 group-dev-v1.json 终端 U）")
    parser.add_argument("--panel-boundary", default=None,
                        help="action_value_v1：工程面板边界说明")
    parser.add_argument("--budget-note", default=None,
                        help="action_value_v1：预算说明（进 TaskContract）")
    parser.add_argument("--three-segment-feedback", default=None,
                        help="action_value_v1 M1：三段反馈 JSON（facts/associated_results/"
                             "mechanism_hypothesis；§8.2 格式，不含确认集数据）")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="坐隐 3.1：最小生成闭环脚手架（不含自动上线通道）")
    sub = parser.add_subparsers(dest="command", required=True)

    i1 = sub.add_parser(OPERATOR_I1, help="I1 初始化：任务/允许信息/合同/单位/限制/反例")
    _add_common(i1)
    m1 = sub.add_parser(OPERATOR_M1, help="M1 修订：父代 + 反馈")
    _add_common(m1)

    load = sub.add_parser("load", help="只做隔离装载（G-0 同级），不产生血缘记录")
    load.add_argument("--code", required=True)
    load.add_argument("--out", required=True)
    load.add_argument("--params", default="{}")
    load.add_argument("--load-timeout-sec", type=float, default=None)

    surface = sub.add_parser("surface", help="打印并核验允许面（提示词里的事实清单）")
    surface.add_argument("--out", default=None)

    budget = sub.add_parser("budget", help="打印调用台账")
    budget.add_argument("--out", required=True)
    budget.add_argument("--calls-budget", type=int, default=None)

    args = parser.parse_args(argv)
    if args.command == OPERATOR_I1:
        return _run_generate(args, OPERATOR_I1)
    if args.command == OPERATOR_M1:
        return _run_generate(args, OPERATOR_M1)
    if args.command == "load":
        return _run_load(args)
    if args.command == "surface":
        return _run_surface(args)
    if args.command == "budget":
        return _run_budget(args)
    parser.error("未知命令：{0}".format(args.command))
    return 2


def _main_with_internal(argv: Optional[Sequence[str]] = None) -> int:
    """带内部入口解析的主函数；先识别 `--internal-load`（子进程专用）。

    **GL-3**：预算耗尽（调用次数或累计 token）不是程序缺陷，而是**按纪律停止**：
    台账已经在 reserve/check 里保存过状态，这里把它转成明确的退出码与提示，
    而不是让 `BudgetExhausted` 以未捕获异常的形式冒到用户面前。
    """

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "--internal-load":
        internal = argparse.ArgumentParser(description="内部：隔离装载入口")
        internal.add_argument("--internal-load", action="store_true")
        internal.add_argument("--code", required=True)
        internal.add_argument("--params", default="{}")
        internal.add_argument("--out", required=True)
        return _internal_load(internal.parse_args(raw_argv))
    try:
        return main(raw_argv)
    except BudgetExhausted as exc:
        # 预算耗尽 = 按纪律停止（状态已保存）；给明确退出码，不让异常裸奔。
        print("预算用尽，已保存状态并停止：{0}".format(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(_main_with_internal())

__all__ = [
    "ALLOWED_IMPORTS",
    "ApiBackend",
    "AttemptContext",
    "BACKENDS",
    "BUDGET_SCHEMA",
    "BudgetExhausted",
    "CONTRACT_SCHEMA",
    "DelegateBackend",
    "GENERATION_RECORD_SCHEMA",
    "GenerationBudget",
    "LOAD_REPORT_SCHEMA",
    "ModelReply",
    "PARSE_AMBIGUOUS_CODE",
    "PARSE_EMPTY",
    "PARSE_MISSING_CODE",
    "PARSE_MISSING_THOUGHT",
    "PARSE_OK",
    "ParsedReply",
    "PromptPacket",
    "REPLY_FILE_SCHEMA",
    "ReplyEnvelopeError",
    "ReplayBackend",
    "SamplingSpec",
    "ScanReport",
    "TaskContract",
    "TransportError",
    "attempt_dir_name",
    "attempt_identity",
    "build_i1_prompt",
    "build_m1_prompt",
    "check_surface",
    "cold_start_probe",
    "default_task_contract",
    "emit_prompt",
    "feedback_from_diagnosis",
    "ingest_reply",
    "load_reply_envelope",
    "parse_model_reply",
    "parent_binding",
    "prepare_attempt",
    "scan_generated_code",
    "supervised_load",
    "write_summary",
]
