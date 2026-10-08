"""坐隐 3.4/3.5：搜索闭环驱动与冻结交接（生成 → 门禁 → 评估 → 有限升级 → 阶段比较 → 冻结）。

**本模块只做“串联与记账”**，不重新实现任何一步：生成/解析/隔离装载交给
sitin_generate.py，三道门禁交给 sitin_gates.py，同面板桌赛与分级淘汰交给
sitin_scheduler.py，阶段合同与阶段编排交给 sitin_stage.py。本模块的职责只有四件：

  1. **冻结预算与停止规则**（四维 × 两账），并在执行前把“这一批要花多少”算清楚；
  2. **先预留后执行**的台账：调用次数 / 输出 token / 桌数 / 墙钟分别记账，
     搜索账与确认账**分开**，超限即保存状态停止并报缺口，**不静默扩容**；
  3. **同面板、可追溯的候选档案**：身份、参数、准入依据、样本面板、根级误差、
     淘汰原因与“未分辨”标记；
  4. **冻结交接**：候选依赖/参数、覆盖、根级误差、阶段情景差、缺口，
     并**分开**报告三种完成状态（工具完成 / 发现候选 / 通过发布门禁）。

**为什么必须单独有这一层**（PLAN-REVISION §5.2 的伪代码正是本模块的合同）：
现有三个工具各自只回答一段问题——生成端不知道评估要花多少桌，评估端不知道
候选从哪来、结论去哪，阶段端不装载候选。没有这一层，“按预算搜索”会退化成
“手工按顺序敲三条命令”，而预算、面板与停止规则就无法在运行前冻结。

**边界（与派单约束逐条对应）**：
  - **不导入候选注册表、不执行候选代码**（REVIEW-9「装载有界」）：需要身份时一律走
    sitin_gates.supervised_prepare 的受监管子进程；本模块自身只 import 标准库与同目录工具。
  - **不注册候选、不改受控契约、不改线上默认策略与配置**：生成产物一律停在
    pending_registration，注册请求只写进交接报告，由人审执行。
  - **不训练任何自适应模型**；生成调用只在离线通道内进行。
  - **不进入第四阶段独立确认**：确认账（confirm）在本轮**结构性不可动用**，
    任何确认账预留一律拒绝（ConfirmAccountFrozen）。
  - **同一身份 + 同一面板只执行一次**；确需重演必须显式 --allow-rerun 并照常计费。
  - 所有产物只写 --out；--out 落在受控源码面（src/、.git/）会被直接拒绝。

**墙钟口径**：wall_clock_sec 是**墙上时钟秒**（实测耗时结算）；预留按**冻结件声明的实测**
wall_estimate_sec_per_table（缺声明即报错；历史常数 1.58125 **已作废**，只在显式一次性处置路径里出现）乘安全系数估计。
预计值与实测值都留在台账里，估计偏差不隐藏。
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
import fcntl
import hashlib
import json
import math
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (Any, Dict, Iterable, List, Mapping, MutableMapping,
                    Optional, Sequence, Tuple)

REPO_ROOT = _PROJECT_ROOT
TOOLS_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')

# 产物 schema（每个都带版本号，便于下游按版本解析）
FREEZE_SCHEMA = "sitin-search-freeze/1"
PLAN_SCHEMA = "sitin-search-plan/1"
LEDGER_SCHEMA = "sitin-search-ledger/1"
ARCHIVE_SCHEMA = "sitin-search-archive/1"
STATE_SCHEMA = "sitin-search-state/1"
HANDOFF_SCHEMA = "sitin-search-handoff/1"
POOL_SCHEMA = "sitin-candidate-pool/1"
GENERATION_PLAN_SCHEMA = "sitin-generation-plan/1"
#: 「越过已报告超限」的知情记录（一行一条，只追加不覆盖）。
OVERRUN_ACK_SCHEMA = "sitin-overrun-acknowledgement/1"
OVERRUN_ACK_FILE = "overrun-acknowledgements.jsonl"

#: 四个预算维度。**必须分开记账**：桌数便宜不等于调用便宜，token 不等于墙钟。
AXES: Tuple[str, ...] = ("calls", "output_tokens", "tables", "wall_clock_sec")
ACCOUNT_SEARCH = "search"
ACCOUNT_CONFIRM = "confirm"

#: 判定"本步是否真的占过预算"时看的维度：**产出型**资源（调用 / 输出 token / 桌数）。
#: 墙钟是伴随量，不进这个判据——否则"启动即崩、只花了 0.05 秒"也会把该步永久锁死，
#: 而墙钟该不该超限由 overrun 规则管（重试时的墙钟预留照样计在 remaining 上，没有免费重试）。
CHARGED_AXES: Tuple[str, ...] = ("calls", "output_tokens", "tables")

#: **历史**扩展曲线的墙钟口径（PLAN-REVISION §6.1：1 进程 25.30 秒 / 16 桌）。
#:
#: **本常数已作废**（回合 6 三本独立诊断账定性：实测每桌 7.4—9.3 秒，它在**产生它的那棵代码树上**
#: 都不复现；差距来自运行时退回了纯 Python 解析路径，不是机器竞争）。因此它**不得再作为任何默认值**：
#: 冻结件必须声明实测的 wall_estimate_sec_per_table；缺字段即**报错**（见 WallBasisMissing）。
#: 唯一例外是"产生于本规则生效之前"的旧冻结件，且必须由调用方用 --legacy-wall-basis **显式点名**、
#: 记进产物与交接件——**不保留静默回落**。
LEGACY_SECONDS_PER_TABLE = 25.30 / 16.0
#: 墙钟基准字段名（冻结件里必须声明的那一个）。
WALL_BASIS_FIELD = "wall_estimate_sec_per_table"
#: "显式一次性处置"的落盘文件名（一行一条，只追加）。
WALL_BASIS_FILE = "wall-basis-declarations.jsonl"
#: 预留用安全系数：估算不是承诺，实测结算才是账。
WALL_SAFETY_FACTOR = 3.0
#: 受监管执行的 SIGTERM→SIGKILL 宽限（秒）。
TOOL_GRACE_SEC = 5.0

#: 三种完成状态（派单要求分开报，不得用一个“完成”混合三种含义）。
COMPLETION_TOOL = "工具完成"
COMPLETION_CANDIDATES = "发现候选"
COMPLETION_RELEASE_GATE = "通过发布门禁"


# ============================================================ 0. 通用工具

def utc_now() -> str:
    """UTC 墙上时钟时间（ISO 8601，秒级）。**持续时间另记**，不从本串反推。"""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    """稳定序列化：面板身份与冻结摘要都建立在它上面，键序不得随插入顺序漂移。"""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def short(digest: Optional[str], length: int = 12) -> str:
    return (digest or "")[:length]


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _deps():
    """依赖登记表模块（tools/sitin_deps.py）——**唯一**不经登记检查加载的 sibling。

    它是登记检查的判据来源，自己不可能再被登记一次（否则成环）。加载方式与
    `_sibling` 相同（先查 sys.modules，再按文件 exec），但显式标注这条自举例外，
    避免“登记表自己不在清单里”成为新的静默缺口：`sitin_deps.py` 由
    `sitin_deps.ENTRY_FILES` 显式列入口，随清单一起摘要。
    """

    cached = _SIBLINGS.get("sitin_deps")
    if cached is not None:
        return cached
    existing = sys.modules.get("sitin_deps")
    if existing is not None and Path(
            getattr(existing, "__file__", "") or "") == _project_file(_PROJECT_ROOT, TOOLS_DIR / "sitin_deps.py"):
        _SIBLINGS["sitin_deps"] = existing
        return existing
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("sitin_deps", _project_file(_PROJECT_ROOT, TOOLS_DIR / "sitin_deps.py"))
    module = _ilu.module_from_spec(spec)
    sys.modules["sitin_deps"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    _SIBLINGS["sitin_deps"] = module
    return module


def _sibling(name: str):
    """按名加载同目录工具模块（只加载一次）。

    与 sitin_scheduler.sibling 同一约定；差别只在**先查 sys.modules**：
    调度器/门禁可能已经把 sitin_process 等装进来了，重复 exec 会得到两份模块对象
    （各自持有自己的缓存），排查时容易看成“两份不同的实现”。

    S2/P3：装载前**先过登记检查**——名字不在 sitin_deps.SIBLING_MODULES 里即
    失败关闭（UnregisteredSiblingLoad），不静默跳过。理由见 sitin_deps 模块 docstring：
    动态装载的实现不进清单时旧结果可以跨实现复用，而这一点事后无法察觉。
    """

    _deps().require_sibling(name, loader="_sibling")
    cached = _SIBLINGS.get(name)
    if cached is not None:
        return cached
    existing = sys.modules.get(name)
    if existing is not None and Path(getattr(existing, "__file__", "") or "") == _project_file(_PROJECT_ROOT, TOOLS_DIR / (name + ".py")):
        _SIBLINGS[name] = existing
        return existing
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location(name, _project_file(_PROJECT_ROOT, TOOLS_DIR / (name + ".py")))
    module = _ilu.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    _SIBLINGS[name] = module
    return module


_SIBLINGS: Dict[str, Any] = {}


def tool_python() -> Path:
    """跑同目录工具的解释器：优先仓库 venv（与人工跑同一条链路）。"""

    venv = _project_file(_PROJECT_ROOT, REPO_ROOT / ".venv/bin/python")
    return venv if venv.is_file() else Path(sys.executable)


def resolve_path(value: Any) -> Path:
    """把请求里的路径解析成绝对路径：相对路径以**仓库根**为基准。

    工具是以 run 目录为 cwd 被调用的，若按 cwd 解析，"fixtures/x.json" 这类
    仓库根相对路径会在产物目录里找不到——那正是"复跑命令不可复制"的常见成因。
    """

    path = Path(str(value))
    return path if path.is_absolute() else (_project_file(_PROJECT_ROOT, REPO_ROOT / path))


def guard_out_dir(path: Path) -> Path:
    """拒绝把产物写进受控源码面。

    与 sitin_generate.guard_out_dir 同一条纪律（一次手滑的 --out 就能把生成代码
    写进候选注册表）。本模块额外拒绝 src/ 与 .git/：这一层不做任何代码发布。
    """

    resolved = Path(path).resolve()
    forbidden = (_project_file(_PROJECT_ROOT, REPO_ROOT / "src"), _project_file(_PROJECT_ROOT, REPO_ROOT / ".git"))
    for root in forbidden:
        if resolved == root or root in resolved.parents:
            raise ValueError(
                "拒绝把搜索产物写进受控源码面：{0}（在该目录下写文件等于绕过人工审核）".format(resolved))
    if resolved == REPO_ROOT:
        raise ValueError("拒绝把搜索产物直接写进仓库根：{0}".format(resolved))
    return resolved


# ============================================================ 1. 冻结预算与停止规则

#: 冻结文件必须给出的停止规则键；缺一项就拒绝开工。
REQUIRED_STOP_RULES: Tuple[str, ...] = (
    "keep_fraction", "exploration_slots", "upgrade_slots",
    "consecutive_failures", "unresolved_rule", "on_budget_exhausted",
    "on_panel_mismatch", "rerun",
    # 用量不可核对的调用次数上限：token 预算有**两个**约束维度，
    # 未知量既保守计入 spent，又单独计数封顶，不允许用"读不到"绕过预算。
    "unknown_token_call_limit",
)


@dataclass(frozen=True)
class Freeze:
    """冻结的预算与停止规则；**运行中不得改变**（改了摘要就对不上，台账会拒绝加载）。

    为什么要摘要：预算与停止规则如果在运行中可变，“到预算即停”就变成一句口号。
    台账里存 freeze_sha256，第二次运行发现摘要不同就直接拒绝，而不是把两套规则
    记进同一本账。
    """

    path: Path
    data: Mapping[str, Any]
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "Freeze":
        path = Path(path)
        if not path.is_file():
            raise ValueError("冻结文件不存在：{0}".format(path))
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, Mapping) or data.get("schema") != FREEZE_SCHEMA:
            raise ValueError("冻结文件 schema 必须是 {0}，得到 {1!r}".format(
                FREEZE_SCHEMA,
                (data or {}).get("schema") if isinstance(data, Mapping) else None))
        accounts = data.get("accounts") or {}
        for account in (ACCOUNT_SEARCH, ACCOUNT_CONFIRM):
            limits = accounts.get(account)
            if not isinstance(limits, Mapping):
                raise ValueError("冻结文件缺少账户 {0}".format(account))
            missing = [axis for axis in AXES if axis not in limits]
            if missing:
                raise ValueError("账户 {0} 缺少维度 {1}（四维必须齐全，缺一不可记账）".format(
                    account, missing))
        for key in ("panel", "upgrade", "stage"):
            if not isinstance(data.get(key), Mapping):
                raise ValueError("冻结文件缺少 {0} 段".format(key))
        rules = data.get("stop_rules") or {}
        missing_rules = [key for key in REQUIRED_STOP_RULES if key not in rules]
        if missing_rules:
            raise ValueError("冻结文件 stop_rules 缺少 {0}（停止规则必须在运行前冻结）".format(
                missing_rules))
        return cls(path=path, data=data, sha256=sha256_text(raw))

    def limit(self, account: str, axis: str) -> float:
        return float(self.data["accounts"][account][axis])

    @property
    def accounts(self) -> Mapping[str, Any]:
        return self.data["accounts"]

    @property
    def stop_rules(self) -> Mapping[str, Any]:
        return self.data["stop_rules"]

    @property
    def panel(self) -> Mapping[str, Any]:
        return self.data["panel"]

    @property
    def upgrade(self) -> Mapping[str, Any]:
        return self.data["upgrade"]

    @property
    def stage(self) -> Mapping[str, Any]:
        return self.data["stage"]

    @property
    def retry_reserve_tables(self) -> int:
        return int(self.data.get("retry_reserve_tables", 0))

    def wall_basis(self, legacy_reason: Optional[str] = None) -> Dict[str, Any]:
        """墙钟估算的基准（秒/桌）：**必须来自冻结件的实测声明**，否则报错。

        为什么 fail-closed（Lead 裁定 2026-09-15 F2）：本模块曾经"没声明就回落到历史常数 1.58125"，
        而那个常数**已作废**——于是"新冻结必须声明实测值"只落在文案上，机器不拦；本轮 L1b/L2b 的墙钟超限
        正是这个回退踩出来的。所以现在：缺字段 ⇒ 抛 WallBasisMissing，**不静默补值、不只告警**。

        唯一例外：产生于本规则生效之前的旧冻结件（例如 search-freeze.json / stage-v2.json）。
        对它们必须由调用方传 legacy_reason（一句话说明）**显式点名**，返回值里带
        source="legacy-declared" 与原因，供产物与交接件如实披露——这不是兼容通道，是**一次性处置路径**。
        """

        value = self.data.get(WALL_BASIS_FIELD)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"seconds_per_table": float(value), "source": "declared", "reason": "",
                    "freeze_path": str(self.path), "freeze_sha256": self.sha256}
        if not str(legacy_reason or "").strip():
            raise WallBasisMissing(
                "冻结件 {0} 未声明 {1}：**不得静默回落历史常数**（{2} 已作废）。"
                "请在该件里声明实测值；若它产生于本规则生效之前，须用 "
                "--legacy-wall-basis 显式声明一次性处置（一句话原因），并计入产物与交接件。"
                .format(self.path, WALL_BASIS_FIELD, LEGACY_SECONDS_PER_TABLE))
        return {"seconds_per_table": LEGACY_SECONDS_PER_TABLE, "source": "legacy-declared",
                "reason": str(legacy_reason).strip(),
                "value_note": "历史口径（非实测）：该冻结件产生于 fail-closed 规则生效之前",
                "freeze_path": str(self.path), "freeze_sha256": self.sha256}

    def limits_of(self, account: str) -> Dict[str, float]:
        return {axis: self.limit(account, axis) for axis in AXES}


# ============================================================ 2. 预算台账（四维 × 两账）

class WallBasisMissing(RuntimeError):
    """冻结件没有声明实测墙钟基准，且调用方也没有给出显式的一次性处置声明。

    **不许有默认值**：本模块的默认值曾经是已作废的历史常数，而"缺声明"与"声明了历史值"
    在产物里必须能分辨——前者是错误，后者是被点名的例外。
    """


class BudgetExhausted(RuntimeError):
    """预算不足：**保存状态并停止，报告缺口**；不静默扩容。"""


class ConfirmAccountFrozen(RuntimeError):
    """本轮不进入第四阶段独立确认：确认账**不可动用**。

    搜索账不足时，唯一正确的动作是停止并报缺口——把确认账挪来搜索会让
    “独立确认”在统计上不再独立（确认预算必须留给候选冻结之后的第一次使用）。
    """


@dataclass
class SearchLedger:
    """搜索台账：reservations 是唯一事实来源，spent / reserved 都由它推出。

    **纪律**（与调度器/生成台账同源）：
      ① **先预留后执行**——预留时就落盘；执行前预算不足 ⇒ 抛 BudgetExhausted；
      ② **失败与重试同样计费**——settle 默认按预留额全额计费（actual 只在有实测值时给）；
      ③ **释放必须给理由**——release 只用于“确实没有执行”（例如能力探针判定不可用），
         理由进台账；这条让“预算去哪了”永远可核对。
    """

    path: Path
    freeze_sha256: str
    limits: Dict[str, Dict[str, float]]
    reservations: List[Dict[str, Any]] = field(default_factory=list)

    # --- 账目视图 ---------------------------------------------------------
    def _sum(self, account: str, status: str) -> Dict[str, float]:
        totals = {axis: 0.0 for axis in AXES}
        for item in self.reservations:
            if item["account"] != account or item["status"] != status:
                continue
            amounts = item["amounts"] if status == "reserved" else item["charged"]
            for axis in AXES:
                totals[axis] += float(amounts.get(axis, 0.0))
        return totals

    def reserved(self, account: str) -> Dict[str, float]:
        return self._sum(account, "reserved")

    def spent(self, account: str) -> Dict[str, float]:
        return self._sum(account, "settled")

    def remaining(self, account: str) -> Dict[str, float]:
        reserved, spent = self.reserved(account), self.spent(account)
        return {axis: self.limits[account][axis] - reserved[axis] - spent[axis]
                for axis in AXES}

    def unknown_token_calls(self, account: str) -> int:
        """输出 token 用量**读不到**的调用次数（单独计数，不混进已知累计）。"""

        return sum(1 for item in self.reservations
                   if item["account"] == account and item["status"] == "settled"
                   and item.get("tokens_unknown"))

    def unknown_token_charged(self, account: str) -> float:
        """这些调用按预留额保守计入的 token 量（用于说明"账里有多少是估的"）。"""

        return sum(float(item["charged"].get("output_tokens", 0.0))
                   for item in self.reservations
                   if item["account"] == account and item["status"] == "settled"
                   and item.get("tokens_unknown"))

    def has_step(self, step_id: str) -> bool:
        return any(item["step_id"] == step_id for item in self.reservations)

    def has_charged_step(self, step_id: str) -> bool:
        """本步是否**真的占过预算**；`released` 与"四维全 0 的结算"都不算。

        为什么要分开（两条都是实测撞出来的）：
          - `released` 的定义就是"确实没有执行、预算已退回"，一维都没花；把它算成"已有预留"，
            一次 `--dry-run` 就会把该步**永久锁死**（真实运行在预留阶段直接报错）；
          - 反过来，结算时四维**全为 0** 意味着"跑是跑了、什么也没产出"（本轮吞吐账第一次跑就撞上：
            臂进程启动即 SIGSEGV，0 桌、0 秒、0 token）。这种情况照"失败同样计费"去扣满额，
            等于为一次崩溃收 12 桌；而拒绝重试又会让操作者只能靠换目录绕过账本。
        """

        for item in self.reservations:
            if item["step_id"] != step_id or item["status"] == "released":
                continue
            amounts = item["amounts"] if item["status"] == "reserved" else item["charged"]
            if any(float(amounts.get(axis) or 0.0) > 0 for axis in CHARGED_AXES):
                return True
        return False

    def pending_reservation(self, step_id: str) -> Optional[Dict[str, Any]]:
        """本步**已预留但未结算**的那条记录（崩溃恢复用）；没有就返回 None。"""

        for item in self.reservations:
            if item["step_id"] == step_id and item["status"] == "reserved":
                return item
        return None

    def step_ids(self) -> List[str]:
        return [item["step_id"] for item in self.reservations]

    # --- 记账动作 ---------------------------------------------------------
    def reserve(self, *, step_id: str, account: str, amounts: Mapping[str, float],
                note: str) -> Dict[str, Any]:
        """预留一次执行的预算；不足即**落盘并抛错**（绝不静默扩容）。"""

        if account == ACCOUNT_CONFIRM:
            raise ConfirmAccountFrozen(
                "本轮不进入第四阶段独立确认：确认账不可动用（步 {0}）。"
                "搜索不足时请停止并报告缺口，不得把确认预算挪作搜索消耗。".format(step_id))
        if account not in self.limits:
            raise ValueError("未知账户 {0!r}".format(account))
        if self.has_charged_step(step_id):
            raise ValueError("步 {0} 已有预留记录：同一身份不应重复预留（缓存复用或显式重演）".format(
                step_id))
        unknown = [axis for axis in amounts if axis not in AXES]
        if unknown:
            raise ValueError("未知预算维度 {0}（四维之外的开销不得记账）".format(unknown))
        wanted = {axis: float(amounts.get(axis, 0.0)) for axis in AXES}
        remaining = self.remaining(account)
        over = {axis: value for axis, value in wanted.items() if value > remaining[axis] + 1e-9}
        if over:
            self.save()
            raise BudgetExhausted(
                "步 {0} 需要 {1}，账户 {2} 余额不足（缺口 {3}）；"
                "**已保存状态并停止，不静默扩容**".format(
                    step_id,
                    {axis: wanted[axis] for axis in over},
                    account,
                    {axis: round(wanted[axis] - remaining[axis], 3) for axis in over}))
        reservation = {
            "reservation_id": "{0}#{1}".format(step_id, len(self.reservations) + 1),
            "step_id": step_id,
            "account": account,
            "amounts": wanted,
            "note": note,
            "at_utc": utc_now(),
            "status": "reserved",
            "charged": {axis: wanted[axis] for axis in AXES},
        }
        self.reservations.append(reservation)
        self.save()
        return reservation

    def settle(self, reservation: Mapping[str, Any], *, status: str,
               actual: Optional[Mapping[str, float]] = None, note: str = "",
               tokens_unknown: bool = False) -> Dict[str, Any]:
        """结算：actual=None 表示按**预留额全额计费**（失败与重试同样计费）。

        实测值大于预留额时照实记账（overrun=True）——把超支藏起来比超支本身更危险。

        tokens_unknown=True 表示**这次调用的输出 token 用量读不到**：此时按预留额
        保守全额计费，并在台账里单独计数（unknown_token_calls）。"读不到"绝不按 0 记账：
        按 0 会让"未知消耗"变成绕过预算的免费通道。
        """

        target = self._find(reservation)
        if target["status"] != "reserved":
            raise ValueError("预留 {0} 已经结算过（{1}）".format(
                target["reservation_id"], target["status"]))
        charged = dict(target["amounts"])
        if actual is not None:
            for axis, value in actual.items():
                charged[axis] = float(value)
        target.update({"status": "settled", "charged": charged, "settled_status": status,
                       "settled_at_utc": utc_now(), "settled_note": note,
                       "tokens_unknown": bool(tokens_unknown),
                       "overrun": any(charged[axis] > target["amounts"][axis] + 1e-9
                                      for axis in AXES)})
        self.save()
        return target

    def correct(self, reservation: Mapping[str, Any], *, actual: Mapping[str, float],
                note: str) -> Dict[str, Any]:
        """**更正已结算的已知错值**（不改状态、不新增预留），并把更正留痕。

        为什么必须有这条：账本自称唯一事实来源，就不能留着"已知是错的"数字
        （本轮阶段步的 wall_clock_sec=0.0 / overrun=false 就是这种情况——执行件实测
        1250.62 秒，而恢复路径没拿到 elapsed）。**更正而不是重结**：重结会让同一笔开销
        出现两条记录，"到底花了多少"又要靠人判断哪条算数。
        """

        target = self._find(reservation)
        if target["status"] != "settled":
            raise ValueError("只能更正**已结算**的预留；{0} 当前是 {1}".format(
                target["reservation_id"], target["status"]))
        before = dict(target["charged"])
        after = dict(before)
        for axis, value in actual.items():
            if axis not in AXES:
                raise ValueError("未知预算维度 {0}".format(axis))
            after[axis] = float(value)
        if not note.strip():
            raise ValueError("更正必须给出理由（账本要能解释每个数字是怎么来的）")
        target.setdefault("corrections", []).append(
            {"at_utc": utc_now(), "before": before, "after": after, "note": note})
        target["charged"] = after
        target["overrun"] = any(after[axis] > target["amounts"][axis] + 1e-9 for axis in AXES)
        self.save()
        return target

    def overrun_steps(self, account: Optional[str] = None) -> List[str]:
        """已结算且**超出预留**的步——"超限即停"的判据（四维一视同仁，含墙钟）。"""

        return sorted({item["step_id"] for item in self.reservations
                       if item["status"] == "settled" and item.get("overrun")
                       and (account is None or item["account"] == account)})

    def release(self, reservation: Mapping[str, Any], *, reason: str) -> Dict[str, Any]:
        """撤回预留；**只用于确实没有执行的步**，理由必须写清楚。"""

        target = self._find(reservation)
        if target["status"] != "reserved":
            raise ValueError("预留 {0} 已经结算过（{1}）".format(
                target["reservation_id"], target["status"]))
        if not reason.strip():
            raise ValueError("释放预留必须给出理由，否则预算去向无法核对")
        target.update({"status": "released", "release_reason": reason,
                       "released_at_utc": utc_now(), "charged": {axis: 0.0 for axis in AXES}})
        self.save()
        return target

    def _find(self, reservation: Mapping[str, Any]) -> Dict[str, Any]:
        for item in self.reservations:
            if item["reservation_id"] == reservation.get("reservation_id"):
                return item
        raise KeyError("台账里没有这条预留：{0}".format(reservation.get("reservation_id")))

    # --- 落盘 -------------------------------------------------------------
    def to_json(self) -> Dict[str, Any]:
        return {
            "schema": LEDGER_SCHEMA,
            "freeze_sha256": self.freeze_sha256,
            "limits": self.limits,
            "reservations": list(self.reservations),
            "accounts": {
                account: {"limits": self.limits[account],
                          "reserved": self.reserved(account),
                          "spent": self.spent(account),
                          "remaining": self.remaining(account),
                          # 用量读不到的调用**单独计数**：既照实保守计入 spent，
                          # 又让"账里有多少是估的"一眼可见（Lead 口径要求）。
                          "unknown_token_calls": self.unknown_token_calls(account),
                          "unknown_token_charged": self.unknown_token_charged(account)}
                for account in (ACCOUNT_SEARCH, ACCOUNT_CONFIRM)},
        }

    def save(self) -> None:
        write_json(self.path, self.to_json())

    @classmethod
    def load_for_report(cls, path: Path, freeze: Freeze) -> "SearchLedger":
        """**只读汇总**用：不校验冻结摘要（执行路径仍必须走 `load`）。

        多轮执行各有各的冻结与摘要，汇总时要并列而不是互相否决；校验留在执行路径。
        """

        path = Path(path)
        if not path.is_file():
            return cls(path=path, freeze_sha256=freeze.sha256,
                       limits={account: freeze.limits_of(account)
                               for account in (ACCOUNT_SEARCH, ACCOUNT_CONFIRM)})
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != LEDGER_SCHEMA:
            raise ValueError("台账 schema 不符：{0!r}".format(data.get("schema")))
        return cls(path=path, freeze_sha256=str(data.get("freeze_sha256") or ""),
                   limits={account: {axis: float(value) for axis, value in
                                     (data["limits"][account]).items()}
                           for account in (ACCOUNT_SEARCH, ACCOUNT_CONFIRM)},
                   reservations=list(data.get("reservations", ())))

    @classmethod
    def load(cls, path: Path, freeze: Freeze) -> "SearchLedger":
        path = Path(path)
        if not path.is_file():
            return cls(path=path, freeze_sha256=freeze.sha256,
                       limits={account: freeze.limits_of(account)
                               for account in (ACCOUNT_SEARCH, ACCOUNT_CONFIRM)})
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != LEDGER_SCHEMA:
            raise ValueError("台账 schema 不符：{0!r}".format(data.get("schema")))
        if data.get("freeze_sha256") != freeze.sha256:
            raise ValueError(
                "冻结摘要与台账不一致：台账 {0}，本次 {1}。"
                "预算/停止规则改变后不得续用同一本账，请换 --out 重新开始。".format(
                    short(data.get("freeze_sha256")), short(freeze.sha256)))
        return cls(path=path, freeze_sha256=freeze.sha256,
                   limits={account: {axis: float(value) for axis, value in
                                     (data["limits"][account]).items()}
                           for account in (ACCOUNT_SEARCH, ACCOUNT_CONFIRM)},
                   reservations=list(data.get("reservations", ())))


# ============================================================ 3. 面板与统计口径

def plan_level(*, level: str, roots: int, seats: int, seed_base: int,
               root_prefix: str) -> Dict[str, Any]:
    """按与调度器**同一条公式**生成根组与面板身份。

    公式必须一致，否则“我预留的桌数”与“工具实际跑的牌山”会对不上：
    调度器 main 里是 seed = seed_base + offset + i、
    scenario_id = "<prefix>L<index+1>-<i>"，单次调用（只有一个等级）时 index=0。
    本模块**每次调用只跑一个等级**，因此这里同样取 L1，靠不同的
    root_prefix 与 seed_base 区分等级（等级名单独记在产物里）。
    """

    if roots < 1:
        raise ValueError("根组数必须 >= 1，得到 {0}".format(roots))
    if not 1 <= seats <= 4:
        raise ValueError("换座数必须在 1—4，得到 {0}".format(seats))
    root_specs = [{"seed": int(seed_base) + index,
                   "scenario_id": "{0}L1-{1}".format(root_prefix, index)}
                  for index in range(int(roots))]
    return {"level": level, "roots": int(roots), "seats": int(seats),
            "root_specs": root_specs, "root_prefix": root_prefix,
            "seed_base": int(seed_base)}


def panel_identity(panel: Mapping[str, Any], *, baseline_id: str, ruleset: str) -> str:
    """面板身份：根组（按 seed）+ 换座数 + 基线 + 规则版本。

    **比较前必须面板一致**（PLAN §5.1）：候选的均值只有在同一批牌山/换座下才可比。
    scenario_id 标签不参与身份（它只是标签，牌山由 seed 决定）——与调度器
    root_set_id_of 同一条理由。
    """

    payload = {
        "roots": [int(item["seed"]) for item in panel["root_specs"]],
        "seats": int(panel["seats"]),
        "baseline_id": baseline_id,
        "ruleset": ruleset,
    }
    return "panel-" + sha256_text(canonical_json(payload))[:12]


def describe_statistics(stats: Mapping[str, Any]) -> Dict[str, Any]:
    """把根级统计折成三态标签；**不是**效应结论，只是开发面板上的“分辨了吗”。

    - unrankable：有效根组 < 2 或本轮运行失败 ⇒ 不参与排序（缺失值绝不补零）；
    - unresolved：|均值| <= 本面板 MDE ⇒ 本面板分辨不出方向，**标未分辨**；
    - resolved_positive / resolved_negative：点估计大于本面板 MDE。

    边界：这里的 MDE 只用于“这批样本够不够分辨方向”的说明，**不是显著性阈值**，
    更不得当成自动晋级规则（PLAN §5.1 明确禁止用均值差超过 MDE 宣称统计胜出）。
    """

    if not stats.get("rankable") or stats.get("mean") is None:
        return {"state": "unrankable",
                "reason": stats.get("rankable_reason") or "本轮没有可用结果",
                "mde": None, "mean": None, "n_roots": int(stats.get("n_roots") or 0)}
    mean = float(stats["mean"])
    mde = stats.get("mde")
    n_roots = int(stats.get("n_roots") or 0)
    if n_roots < 2 or mde is None:
        return {"state": "unrankable", "reason": "有效根组不足（{0}）".format(n_roots),
                "mde": mde, "mean": mean, "n_roots": n_roots}
    sd_root = float(stats.get("sd_root") or 0.0)
    if mean == 0.0 and sd_root == 0.0:
        # **零差异观测**（Lead 裁定 2026-09-15 新增）：逐根差值全为 0 ⇒ 该面板上没有观测到
        # 任何差别。它与"分辨不出方向"是两件事：后者是样本不够，前者是**这批牌山上压根
        # 没有差别可看**。理由不得写成"|0.0| ≤ MDE 0.0 ⇒ 分辨不出方向"（自相矛盾）。
        return {"state": "no_observed_difference",
                "reason": "该面板上**零差异观测**：逐根差值均为 0、根级 sd 为 0，"
                          "本候选在这些牌山上没有产生可见的选择差异；"
                          "这既不等于「无差异」的证明，也不是门禁结论"
                          "（G-2 是否加候选惰性检查留待 3.P 收口轮）",
                "mde": float(mde), "mean": mean, "n_roots": n_roots}
    if abs(mean) <= float(mde):
        return {"state": "unresolved",
                "reason": "|均值| {0} ≤ 本面板 MDE {1}：本面板分辨不出方向".format(
                    round(mean, 4), round(float(mde), 4)),
                "mde": float(mde), "mean": mean, "n_roots": n_roots}
    return {"state": "resolved_positive" if mean > 0 else "resolved_negative",
            "reason": "点估计大于本面板 MDE（{0} > {1}）：方向在本面板可分辨；"
                      "**不构成效果结论**".format(round(abs(mean), 4), round(float(mde), 4)),
            "mde": float(mde), "mean": mean, "n_roots": n_roots}


# ============================================================ 4. 候选档案

@dataclass
class CandidateRecord:
    """一个候选的完整档案：身份、参数、准入依据、每级样本面板、阶段结果与结论。"""

    key: str
    candidate: Optional[str] = None
    identity: Optional[str] = None
    weights: Dict[str, float] = field(default_factory=dict)
    source: Dict[str, Any] = field(default_factory=dict)
    registration: str = "unknown"          # registered / pending_registration / unregistered
    gate: Dict[str, Any] = field(default_factory=dict)
    levels: Dict[str, Any] = field(default_factory=dict)
    stage: Dict[str, Any] = field(default_factory=dict)
    verdict: str = "pending"
    verdict_reason: str = ""
    notes: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return {"key": self.key, "candidate": self.candidate, "identity": self.identity,
                "weights": dict(self.weights), "source": dict(self.source),
                "registration": self.registration, "gate": dict(self.gate),
                "levels": dict(self.levels), "stage": dict(self.stage),
                "verdict": self.verdict, "verdict_reason": self.verdict_reason,
                "notes": list(self.notes)}


@dataclass
class Archive:
    """候选档案集合：**key 是稳定档案键**（已注册候选用注册名，生成产物用尝试身份）。"""

    path: Path
    freeze_sha256: str
    records: Dict[str, CandidateRecord] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def upsert(self, key: str, **fields: Any) -> CandidateRecord:
        record = self.records.get(key)
        if record is None:
            record = CandidateRecord(key=key)
            self.records[key] = record
        for name, value in fields.items():
            setattr(record, name, value)
        return record

    def note(self, key: str, text: str) -> None:
        record = self.upsert(key)
        record.notes.append("{0} {1}".format(utc_now(), text))

    def event(self, kind: str, payload: Mapping[str, Any]) -> None:
        self.events.append(dict(payload, kind=kind, at_utc=utc_now()))

    def to_json(self) -> Dict[str, Any]:
        return {"schema": ARCHIVE_SCHEMA, "freeze_sha256": self.freeze_sha256,
                "records": {key: record.to_json() for key, record in sorted(self.records.items())},
                "events": list(self.events)}

    def save(self) -> None:
        write_json(self.path, self.to_json())

    @classmethod
    def load_for_report(cls, path: Path) -> "Archive":
        """**只读汇总**用：不校验冻结摘要（理由同 SearchLedger.load_for_report）。"""

        path = Path(path)
        if not path.is_file():
            return cls(path=path, freeze_sha256="")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != ARCHIVE_SCHEMA:
            raise ValueError("档案 schema 不符：{0!r}".format(data.get("schema")))
        records: Dict[str, CandidateRecord] = {}
        for key, payload in (data.get("records") or {}).items():
            record = CandidateRecord(key=key)
            for name in ("candidate", "identity", "weights", "source", "registration",
                         "gate", "levels", "stage", "verdict", "verdict_reason", "notes"):
                if name in payload:
                    setattr(record, name, payload[name])
            records[key] = record
        return cls(path=path, freeze_sha256=str(data.get("freeze_sha256") or ""),
                   records=records, events=list(data.get("events", ())))

    @classmethod
    def load(cls, path: Path, freeze: Freeze) -> "Archive":
        path = Path(path)
        if not path.is_file():
            return cls(path=path, freeze_sha256=freeze.sha256)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != ARCHIVE_SCHEMA:
            raise ValueError("档案 schema 不符：{0!r}".format(data.get("schema")))
        if data.get("freeze_sha256") != freeze.sha256:
            raise ValueError("冻结摘要与档案不一致：请换 --out 重新开始，不要把两套规则记进一个档案")
        records: Dict[str, CandidateRecord] = {}
        for key, payload in (data.get("records") or {}).items():
            record = CandidateRecord(key=key)
            for name in ("candidate", "identity", "weights", "source", "registration",
                         "gate", "levels", "stage", "verdict", "verdict_reason", "notes"):
                if name in payload:
                    setattr(record, name, payload[name])
            records[key] = record
        return cls(path=path, freeze_sha256=freeze.sha256, records=records,
                   events=list(data.get("events", ())))


@dataclass
class RunState:
    """编排状态：已完成的步、停止原因。中断后重跑靠它跳过已完成的步（缓存复用）。"""

    path: Path
    completed: List[str] = field(default_factory=list)
    stop_reason: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "RunState":
        path = Path(path)
        if not path.is_file():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != STATE_SCHEMA:
            raise ValueError("状态 schema 不符：{0!r}".format(data.get("schema")))
        return cls(path=path, completed=list(data.get("completed", ())),
                   stop_reason=data.get("stop_reason"), notes=list(data.get("notes", ())))

    def save(self) -> None:
        write_json(self.path, {"schema": STATE_SCHEMA, "completed": list(self.completed),
                               "stop_reason": self.stop_reason, "notes": list(self.notes)})

    def done(self, step_id: str) -> bool:
        return step_id in self.completed

    def mark(self, step_id: str) -> None:
        if step_id not in self.completed:
            self.completed.append(step_id)
        self.save()


# ============================================================ 5. 受监管的工具调用

@dataclass(frozen=True)
class ToolRun:
    """一次工具调用的结局；**保留原样输出**，证据不靠转述。"""

    name: str
    command: Tuple[str, ...]
    returncode: Optional[int]
    timed_out: bool
    elapsed_sec: float
    signals_sent: Tuple[str, ...]
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_json(self, *, tail_chars: int = 4000) -> Dict[str, Any]:
        return {"name": self.name, "command": list(self.command),
                "returncode": self.returncode, "timed_out": self.timed_out,
                "elapsed_sec": round(self.elapsed_sec, 3),
                "signals_sent": list(self.signals_sent),
                "stdout_tail": self.stdout[-tail_chars:],
                "stderr_tail": self.stderr[-tail_chars:]}


def run_tool(name: str, command: Sequence[Any], *, cwd: Path, timeout_sec: float,
             dry_run: bool = False) -> ToolRun:
    """跑一个同目录工具（**受监管**：进程组终止 + 墙钟上限 + 输出留尾）。

    为什么会话外进程要复用门禁/调度器的终止实现：一处只等直接子进程、另一处等整组，
    迟早会产生第二份缺陷（REVIEW-8 S8-2 的教训）。dry_run 时不执行，只留命令。
    """

    rendered = tuple(str(item) for item in command)
    if dry_run:
        return ToolRun(name=name, command=rendered, returncode=None, timed_out=False,
                       elapsed_sec=0.0, signals_sent=(), stdout="", stderr="(dry-run)")
    proc = _sibling("sitin_process")
    result = proc.run_supervised(list(rendered), cwd=Path(cwd),
                                 timeout_sec=float(timeout_sec), grace_sec=TOOL_GRACE_SEC)
    return ToolRun(name=name, command=rendered, returncode=result.returncode,
                   timed_out=bool(result.timed_out), elapsed_sec=float(result.elapsed_sec),
                   signals_sent=tuple(result.signals_sent or ()),
                   stdout=result.stdout or "", stderr=result.stderr or "")


# ============================================================ 6. 候选池与面板对齐

def load_pool(path: Optional[Path], candidates: Sequence[str],
              weights: Sequence[str]) -> Dict[str, Any]:
    """候选池：--pool 文件或 --candidate/--weights 命令行；两者可并用。"""

    pool: Dict[str, Any] = {"candidates": [], "generated": [], "hypotheses": {}}
    if path is not None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema") != POOL_SCHEMA:
            raise ValueError("候选池 schema 必须是 {0}，得到 {1!r}".format(
                POOL_SCHEMA, data.get("schema")))
        pool["candidates"].extend(data.get("candidates", ()))
        pool["generated"].extend(data.get("generated", ()))
        pool["hypotheses"].update(data.get("hypotheses", {}))
    weight_list = list(weights) + ["{}"] * (len(candidates) - len(weights))
    for name, raw in zip(candidates, weight_list):
        pool["candidates"].append({"candidate": name, "weights": json.loads(raw)})
    return pool


def check_panel_alignment(entries: Sequence[Mapping[str, Any]], *, level: str) -> List[str]:
    """同一级里的候选必须同面板；返回问题列表（空表示对齐）。

    **不同面板的均值不可直接比较**（PLAN §5.1）：这不是“更严格”，而是唯一正确的算法——
    换了一批牌山，均值差里就混进了牌山差。
    """

    panels = {entry.get("panel_id") for entry in entries}
    if len(panels) > 1:
        return ["等级 {0} 的候选面板不一致：{1}（跨面板比较被拒绝）".format(
            level, sorted(str(item) for item in panels))]
    if any(not entry.get("panel_id") for entry in entries):
        return ["等级 {0} 存在没有面板身份的候选：跨面板或未声明面板一律不可比".format(level)]
    return []


# ============================================================ 7. 编排上下文

@dataclass
class SearchContext:
    """一次搜索运行的全部句柄；所有产物只落在 out 之下。"""

    out: Path
    freeze: Freeze
    ledger: SearchLedger
    archive: Archive
    state: RunState
    steps_path: Path
    dry_run: bool = False
    allow_rerun: bool = False
    #: 调用方对"产生于 fail-closed 规则之前的冻结件"的**显式一次性声明**（一句话原因）。
    #: 为空时，缺 wall_estimate_sec_per_table 的冻结件会直接报错——**没有静默回落**。
    legacy_wall_basis: Optional[str] = None

    def step(self, step_id: str, *, account: str, amounts: Mapping[str, float],
             note: str) -> Dict[str, Any]:
        """为一步预留预算；已完成的步直接复用（**同一身份不重复执行/计费**）。"""

        if self.state.done(step_id) and not self.allow_rerun:
            self.log({"step_id": step_id, "status": "reused",
                      "note": "该步已完成：复用既有产物，不重复预留与执行"})
            return {"step_id": step_id, "status": "reused"}
        # **崩溃恢复**：台账里已有本步的未结算预留（上一次预留了但没走完结算），
        # 直接**续用**那条预留，而不是再预留一次——否则要么被判重复预留而报错，
        # 要么在 --allow-rerun 下把同一笔开销记两遍（调度器 R7-3 的同一纪律：
        # "不把'没写 done'解释成'从未执行'"）。
        pending = self.ledger.pending_reservation(step_id)
        if pending is not None and not self.allow_rerun:
            self.log({"step_id": step_id, "status": "resumed",
                      "note": "台账已有未结算预留，续用并等待结算（不重复扣款）"})
            return {"step_id": step_id, "status": "resumed", "reservation": pending}
        return {"step_id": step_id, "status": "reserved",
                "reservation": self.ledger.reserve(step_id=step_id, account=account,
                                                   amounts=amounts, note=note)}

    def step_will_reuse(self, step_id: str) -> bool:
        """该步是否会被判"复用"（不执行、不预留、不计费）。

        **为什么要在取资源基准之前先问这一句**（评审 F12）：墙钟基准现在缺声明就报错，
        若在"复用"判定之前取，那么一个**已经全部跑完**的历史账连复跑（什么都不做）都会报错——
        README 里"幂等：已完成的步复用、不重复计费"这句自我描述就不成立了。
        """

        return self.state.done(step_id) and not self.allow_rerun

    def wall_basis(self, freeze: Optional[Freeze] = None) -> Dict[str, Any]:
        """取墙钟基准，并在用到**遗留口径**时把这次一次性处置留痕（可核，不可静默）。"""

        basis = (freeze or self.freeze).wall_basis(self.legacy_wall_basis)
        if basis["source"] == "legacy-declared":
            _record_wall_basis_declaration(self, basis)
        return basis

    def wall_seconds_per_table(self, freeze: Optional[Freeze] = None) -> float:
        """墙钟估算用的"秒/桌"（缺声明即抛 WallBasisMissing）。"""

        return float(self.wall_basis(freeze)["seconds_per_table"])

    def overrun_detail(self, step_id: str) -> Optional[Dict[str, Any]]:
        """本步超出预留的**结构化**明细（四维一视同仁）；没超限返回 None。

        与 overrun_of 分开的理由：调用方要的常常不是一句人读的话，而是"哪一维、预留多少、
        实结多少"——用来写知情记录、交接例外与复核指引。两处各拼一遍必然分叉。
        """

        for item in self.ledger.reservations:
            if item["step_id"] != step_id or not item.get("overrun"):
                continue
            over = {axis: {"预留": item["amounts"][axis], "实结": item["charged"][axis]}
                    for axis in AXES if item["charged"][axis] > item["amounts"][axis] + 1e-9}
            return {"step_id": step_id, "reservation_id": item["reservation_id"],
                    "account": item["account"], "axes": over,
                    "summary": "{0} 超出预留：{1}".format(step_id, canonical_json(over))}
        return None

    def overrun_of(self, step_id: str) -> Optional[str]:
        """本步是否超出预留（四维一视同仁）。**超限即停**的判据由它给出。

        为什么墙钟也要停：四维预算的意义是"花多少看得见、超了就停"；实测吞吐比历史报价
        慢 5 倍时，墙钟恰恰是最容易失控的一维——只记账不停车等于形同虚设（Lead 裁定 2026-09-15）。
        """

        detail = self.overrun_detail(step_id)
        return detail["summary"] if detail else None

    def log(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload.setdefault("at_utc", utc_now())
        self.steps_path.parent.mkdir(parents=True, exist_ok=True)
        with self.steps_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def save(self) -> None:
        self.ledger.save()
        self.archive.save()
        self.state.save()


# ============================================================ 8. 各步实现

def as_gate_dirs(value: Any) -> Tuple[Path, ...]:
    """把 --gate-records 收成一个目录元组（可传单个路径，也可传多个）。

    为什么门禁记录会分散在多处：记录由**产出它的那个包**落在自己的可写目录里，
    "复制一份到别处"会让两份同 schema 的记录必然分叉（Lead 裁定：不做复制）。
    于是消费侧必须能**同时读多处**，否则一条真实存在的准入记录会被读成"没有记录"。
    """

    if value is None:
        return ()
    if isinstance(value, (str, Path)):
        return (Path(value),)
    return tuple(Path(item) for item in value)


#: 跨目录比对门禁记录的字段集：**任何一项不同**即判冲突（fail-closed，不任选其一）。
GATE_RECORD_COMPARE_FIELDS: Tuple[str, ...] = (
    "admitted", "evidence_kind", "bound_identity", "schema",
    "failed", "insufficient", "weights_effective",
)


def _gate_record_differences(records: Sequence[Mapping[str, Any]]) -> List[str]:
    """多处记录之间的**逐字段差异**（空列表 = 完全一致）。

    比对字段取自 GATE_RECORD_COMPARE_FIELDS：只比"会改变准入结论"的字段，
    时间戳一类不作数（不同时间跑的同一结论不算冲突）。
    """

    problems: List[str] = []
    for field in GATE_RECORD_COMPARE_FIELDS:
        values = {canonical_json(item.get(field)) for item in records}
        if len(values) > 1:
            problems.append("{0}：{1}".format(field, sorted(values)[:3]))
    return problems


def _screen_gate_dir(entries: Sequence[Mapping[str, Any]],
                     fallback: Optional[Path] = None) -> Optional[Path]:
    """给调度器的**唯一**一个 --gate-records 目录；队列里不一致时返回 None（调用方 fail-closed 停）。

    为什么必须一致：调度器在扣预算前会**自己再核验一次**准入，而它的参数只接受一个目录。
    记录分散在两处时**不能静默挑一个**——挑错的那个会让部分候选被调度器拒掉、白跑一遍；
    这里宁可停下并指名说清，也不猜。

    三种情形：
      - 队列里所有记录都落在同一个目录 ⇒ 就用它；
      - 队列里**一条记录路径都没有**（准入由调用方注入等）⇒ 退回调用方声明的第一个目录，
        由调度器自己 fail-closed 核验；
      - 落在**多个**目录 ⇒ 返回 None，调用方停止。
    """

    dirs = sorted({str(Path(path).parent)
                   for entry in entries
                   for path in ((entry.get("admission") or {}).get("record_paths") or [])})
    if len(dirs) == 1:
        return Path(dirs[0])
    if not dirs:
        return fallback
    return None


def rescan_admission(ctx: SearchContext, records: Sequence[Mapping[str, Any]], *,
                     gate_dirs: Any, admission_corpus: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """按**当前**门禁记录重扫准入，供**聚合侧**（freeze）修正报告里的 `gate` 字段。

    为什么要这一步：门禁记录会随后续提交出现在**别的目录**里，而档案里的 `gate` 是它自己那次
    运行当时的快照。机器字段若继续写"没有记录"，下游按字面读就会把**已准入**候选当成未准入——
    这比"找不到记录"更危险。重扫只改**报告**：`archive.json` 保留其运行当时的快照，
    并在重扫结果里标 `rescanned_by`，读者能分清哪一个是重扫出来的。
    """

    entries = [{"candidate": item.get("candidate") or item.get("key"),
                "weights": dict(item.get("weights") or {})}
               for item in records if item.get("candidate")]
    if not entries:
        return {}
    results = step_admission(ctx, entries, gate_dirs=gate_dirs, admission_corpus=admission_corpus)
    return {str(item["candidate"]): item for item in results}


def step_admission(ctx: SearchContext, entries: Sequence[Mapping[str, Any]], *,
                   gate_dir: Any = None, admission_corpus: Optional[Path] = None,
                   gate_dirs: Any = None) -> List[Dict[str, Any]]:
    """准入核验（**轻量**）：受监管取身份 + 扫描准入记录；默认不重跑门禁。

    与 sitin_scheduler._gate_admits 同口径（身份一致 + 语料一致 + 至少一条
    evidence_kind=admission 且 admitted=true，结论分歧一律拒绝），
    但**判定权仍在调度器**：它在扣预算前会自己再核验一次。本步只是让“哪些候选
    值得花桌数”在执行前可见，并给出**可区分的失败理由**。
    """

    gates = _sibling("sitin_gates")
    corpus_sha = (sha256_file(admission_corpus)
                  if admission_corpus and Path(admission_corpus).is_file() else None)
    # 门禁记录可以分散在多处（各包落在自己的可写目录）：**一次读多处并合并**。
    dirs = tuple(dict.fromkeys(as_gate_dirs(gate_dirs) + as_gate_dirs(gate_dir)))
    results: List[Dict[str, Any]] = []
    for entry in entries:
        name = entry["candidate"]
        prepared = gates.supervised_prepare(name, entry.get("weights") or {})
        item: Dict[str, Any] = {"candidate": name, "weights": dict(entry.get("weights") or {})}
        if not prepared.get("ok"):
            reason = str(prepared.get("reason") or "受监管装载未通过")
            item.update({"status": "load_failed", "reason": reason,
                         "registration": "unregistered" if "未注册" in reason else "registered"})
            results.append(item)
            continue
        identity = prepared["bound_identity"]
        item.update({"status": "identity", "identity": identity, "registration": "registered"})
        readable = [path for path in dirs if path.is_dir()]
        if not readable:
            item.update({"status": "no_gate_records", "reason": "未提供门禁记录目录",
                         "gate_dirs": [str(path) for path in dirs]})
            results.append(item)
            continue
        matches: List[Tuple[str, Mapping[str, Any]]] = []
        unknown_kind = 0
        scanned: List[Tuple[str, Mapping[str, Any]]] = []
        for gate_root in readable:
            for record_path in sorted(gate_root.glob("*.json")):
                try:
                    data = json.loads(record_path.read_text(encoding="utf-8"))
                except Exception:                   # noqa: BLE001 —— 读不动的记录不参与判定
                    continue
                if not isinstance(data, Mapping):
                    continue
                scanned.append((record_path.name, data))
                if data.get("bound_identity") != identity:
                    continue
                if data.get("evidence_kind") != "admission":
                    unknown_kind += 1
                    continue
                matches.append((str(record_path), data))
        item["gate_dirs"] = [str(path) for path in readable]
        if not matches:
            item.update({"status": "no_admission_record",
                         "reason": "没有与当前候选绑定身份一致的准入记录"
                                   "（缺 evidence_kind 的记录 {0} 条）{1}".format(
                                       unknown_kind, _near_miss_hint(scanned, identity))})
            results.append(item)
            continue
        if corpus_sha is None:
            item.update({"status": "no_corpus", "reason": "未声明准入语料或该文件不可读"})
            results.append(item)
            continue
        same_corpus = [(n, d) for n, d in matches
                       if isinstance(d.get("corpus"), Mapping)
                       and d["corpus"].get("sha256") == corpus_sha]
        if not same_corpus:
            item.update({"status": "corpus_mismatch",
                         "reason": "准入语料与记录不一致（记录 {0}，本次 {1}）".format(
                             sorted({str((d.get("corpus") or {}).get("sha256"))[:12]
                                     for _, d in matches}), short(corpus_sha))})
            results.append(item)
            continue
        verdicts = {bool(d.get("admitted")) for _, d in same_corpus}
        if len(verdicts) > 1:
            item.update({"status": "conflicting_records",
                         "reason": "同一身份同一语料存在结论不一致的记录：{0}（fail-closed 拒绝）".format(
                             sorted(name for name, _ in same_corpus)),
                         "record_paths": sorted(name for name, _ in same_corpus)})
            results.append(item)
            continue
        # **跨目录比对**：同一候选在不止一处有记录时必须逐字段对上。
        # 任选其一等于让"哪一份算数"由目录顺序决定——那是最难查的一类错。
        differences = _gate_record_differences([d for _, d in same_corpus])
        if differences:
            item.update({"status": "conflicting_gate_records",
                         "reason": "同一身份同一语料在**多处**有记录且字段不一致（fail-closed 拒绝）：{0}".format(
                             "；".join(differences)),
                         "record_paths": sorted(name for name, _ in same_corpus),
                         "differences": differences})
            results.append(item)
            continue
        admitted = next(iter(verdicts))
        record_name, record = same_corpus[0]
        item.update({
            "status": "admitted" if admitted else "not_admitted",
            "record": Path(record_name).name,
            "record_path": record_name,
            "record_paths": sorted(name for name, _ in same_corpus),
            "corpus_sha256": corpus_sha,
            "corpus_path": str((record.get("corpus") or {}).get("path")),
            "failed": record.get("failed"),
            "insufficient": record.get("insufficient"),
            "reason": "" if admitted else "记录明确 admitted=false（失败 {0}；证据不足 {1}）".format(
                record.get("failed"), record.get("insufficient")),
        })
        results.append(item)
    return results


def _near_miss_hint(scanned: Sequence[Tuple[str, Mapping[str, Any]]],
                    identity: str) -> str:
    """找不到同身份记录时，给出**近失配**线索：同候选、同源码，只是参数写法不同。

    绑定身份是**字面量敏感**的：JSON 里写 20 与 20.0 会得到两个身份，于是"门禁通过
    的那份配置"与"本次要跑的配置"对不上——这正是 fail-closed 要拦的事。但只报
    "没有记录"会让人以为是记录丢了；这里把近失配的记录列出来，让缺口可定位、可修。
    """

    head, _, _ = identity.partition("|")
    source = identity.rsplit("|", 1)[-1]
    near: List[str] = []
    for name, data in scanned:
        recorded = str(data.get("bound_identity") or "")
        if not recorded or recorded == identity:
            continue
        if recorded.partition("|")[0] == head and recorded.rsplit("|", 1)[-1] == source:
            near.append("{0} 记录为 {1}".format(name, recorded.split("|")[1]
                                                if "|" in recorded else recorded))
    if not near:
        return ""
    return "；**近失配**（同候选同源码、参数写法不同）——{0}".format("；".join(sorted(near)[:3]))


def step_generate(ctx: SearchContext, request: Mapping[str, Any], *, timeout_sec: float,
                  token_reserve: int) -> Dict[str, Any]:
    """一次生成/修订尝试：**先预留调用与 token，再调用**；失败与重试同样计费。"""

    step_id = "generate:{0}".format(request["request_id"])
    plan = ctx.step(step_id, account=ACCOUNT_SEARCH,
                    amounts={"calls": 1, "output_tokens": token_reserve,
                             "wall_clock_sec": timeout_sec},
                    note="生成尝试 {0}（算子 {1}，后端 {2}）".format(
                        request["request_id"], request.get("operator"), request.get("backend")))
    if plan["status"] == "reused":
        return plan
    reservation = plan["reservation"]

    gen_out = ctx.out / "generate" / str(request["request_id"])
    command: List[Any] = [tool_python(), _project_file(_PROJECT_ROOT, TOOLS_DIR / "sitin_generate.py"),
                          str(request.get("operator") or "i1"), "--out", gen_out,
                          "--calls-budget", int(request.get("calls_budget", 4)),
                          "--backend", str(request.get("backend") or "replay"),
                          "--params", json.dumps(request.get("params") or {}, ensure_ascii=False)]
    for key, flag in (("max_total_tokens", "--max-total-tokens"),
                      ("load_timeout_sec", "--load-timeout-sec")):
        if request.get(key) is not None:
            command += [flag, str(request[key])]
    # 路径类参数按**仓库根**解析：生成工具是以 run 目录为 cwd 调用的，而产物里
    # 记仓库根相对路径更可移植（换机器仍能照着复跑）。
    for key, flag in (("parent", "--parent"), ("feedback_file", "--feedback"),
                      ("from_diagnosis", "--from-diagnosis"), ("replay", "--replay"),
                      ("reply_file", "--reply-file")):
        if request.get(key) is not None:
            command += [flag, str(resolve_path(request[key]))]
    before_tokens = _budget_tokens(gen_out)
    run = run_tool("sitin_generate." + str(request.get("operator") or "i1"), command,
                   cwd=ctx.out, timeout_sec=timeout_sec, dry_run=ctx.dry_run)
    parsed = _last_json_object(run.stdout)
    usage = read_token_usage(gen_out=gen_out,
                             attempt_dir=(parsed or {}).get("attempt_dir"),
                             before=before_tokens, after=_budget_tokens(gen_out))
    payload = {"step_id": step_id, "request": dict(request), "tool": run.to_json(),
               "parsed": parsed, "token_usage": usage}
    if ctx.dry_run:
        ctx.ledger.release(reservation, reason="dry-run：只做计划，不执行生成")
        ctx.log(dict(payload, status="dry_run"))
        return payload
    # 用量读不到 ⇒ 按**预留额**保守计费并单独计数；读得到 ⇒ 按实测结算。
    charged_tokens = usage["output_tokens"] if usage["known"] else token_reserve
    if not run.ok or parsed is None:
        # 失败照常计费（失败与重试同样计费）；调用已经发生，用量未知就按预留额计。
        ctx.ledger.settle(reservation, status="failed",
                          actual={"calls": 1, "output_tokens": charged_tokens,
                                  "wall_clock_sec": run.elapsed_sec},
                          note="生成调用未产出可解析结果",
                          tokens_unknown=not bool(usage["known"]))
        ctx.state.mark(step_id)
        ctx.save()
        ctx.log(dict(payload, status="failed"))
        return payload
    ctx.ledger.settle(reservation, status="ok",
                      actual={"calls": 1, "output_tokens": charged_tokens,
                              "wall_clock_sec": run.elapsed_sec},
                      note="生成尝试完成；用量来源 {0}".format(usage.get("source") or "未知"),
                      tokens_unknown=not bool(usage["known"]))
    attempt_dir = parsed.get("attempt_dir")
    key = str(parsed.get("attempt_identity") or request["request_id"])
    # 相对 attempt_dir 的基准是生成端自己的 --out（gen_out），不是本进程的工作目录；
    # 少传这一层就把指纹静默记成 null（见 _code_sha_of 的说明）。
    code_sha = _code_sha_of(attempt_dir, base=gen_out)
    strength = generation_evidence_strength(gen_out, key)
    ctx.archive.upsert(
        key, identity=str(parsed.get("attempt_identity") or ""),
        weights=dict(request.get("params") or {}),
        registration="pending_registration",
        source={"kind": "generated_attempt", "attempt_dir": attempt_dir,
                "code_sha256": code_sha, "operator": request.get("operator"),
                "backend": request.get("backend"), "request_id": request["request_id"],
                "parent": request.get("parent"),
                # 取证强度随产物落盘：决定这条记录进"待静态注册"还是"演练不可注册"缺口。
                "evidence_strength": strength["strength"],
                "evidence_kind": strength.get("evidence_kind"),
                "is_model_output": strength.get("is_model_output"),
                "admission_eligible": strength.get("admission_eligible")},
        gate={"status": "not_run",
              "reason": "生成产物停在 pending_registration：**未静态注册**，门禁与调度都找不到它"},
        verdict="blocked",
        verdict_reason="等待人工静态注册（本模块不做注册，也不改 policy 源码）")
    ctx.archive.note(key, "生成尝试完成：解析 {0}；装载 {1}；准入 {2}".format(
        parsed.get("parse_status"), parsed.get("load_ok"), parsed.get("admission")))
    ctx.state.mark(step_id)
    ctx.save()
    ctx.log(dict(payload, status="ok"))
    return payload


def step_screen(ctx: SearchContext, *, level: str, entries: Sequence[Mapping[str, Any]],
                panel: Mapping[str, Any], spec: Mapping[str, Any],
                gate_dir: Path, admission_corpus: Path, timeout_sec: float) -> Dict[str, Any]:
    """同面板完整桌赛（L1 初筛 / 升级共用）：**先预留全部成本，再交给调度器执行**。"""

    step_id = "screen:{0}".format(level)
    tables = len(entries) * int(panel["roots"]) * int(panel["seats"]) * 2
    note = "{0}：{1} 候选 × {2} 根 × {3} 换座 × 2 臂".format(level, len(entries), panel["roots"],
                                                             panel["seats"])
    # **先在"复用"判定之后才取墙钟基准**（F12）：已完成的步不消费基准，历史账才复跑得动。
    if ctx.step_will_reuse(step_id):
        return ctx.step(step_id, account=ACCOUNT_SEARCH, amounts={}, note=note)
    wall_estimate = tables * ctx.wall_seconds_per_table() * WALL_SAFETY_FACTOR
    plan = ctx.step(step_id, account=ACCOUNT_SEARCH,
                    amounts={"tables": tables, "wall_clock_sec": wall_estimate},
                    note="{0}：{1} 候选 × {2} 根 × {3} 换座 × 2 臂".format(
                        level, len(entries), panel["roots"], panel["seats"]))
    if plan["status"] == "reused":
        return plan
    reservation = plan["reservation"]

    level_dir = ctx.out / "screen" / level
    level_dir.mkdir(parents=True, exist_ok=True)
    # 记下**本次调用之前**调度器台账的累计值：重演（--allow-rerun）时台账会继续累加，
    # 直接取 spent_tables 会把上一轮的消耗重复计到本轮（口径错在"增量"上）。
    spent_before = _scheduler_spent_tables(level_dir / "scheduler-ledger.json")
    command: List[Any] = [tool_python(), _project_file(_PROJECT_ROOT, TOOLS_DIR / "sitin_scheduler.py")]
    for entry in entries:
        command += ["--candidate", entry["candidate"],
                    "--weights", json.dumps(entry.get("weights") or {}, ensure_ascii=False)]
    # 门禁记录与语料一律**解析成绝对路径**再交给工具：子工具是按产物目录为 cwd 调用的，
    # 传仓库根相对路径会让 R7-1 的语料核验直接判"语料不可读"（fail-closed，扣不了预算）。
    command += ["--levels", json.dumps([dict(spec)], ensure_ascii=False),
                "--ledger", level_dir / "scheduler-ledger.json",
                "--out", level_dir, "--budget-tables", tables,
                "--gate-records", resolve_path(gate_dir),
                "--admission-corpus", resolve_path(admission_corpus),
                "--seed-base", int(panel["seed_base"]), "--root-prefix", str(panel["root_prefix"])]
    if ctx.allow_rerun:
        command.append("--allow-rerun")
    run = run_tool("sitin_scheduler." + level, command, cwd=ctx.out,
                   timeout_sec=timeout_sec, dry_run=ctx.dry_run)
    if ctx.dry_run:
        ctx.ledger.release(reservation, reason="dry-run：只做计划，不执行桌赛")
        ctx.log({"step_id": step_id, "status": "dry_run", "tool": run.to_json(),
                 "planned_tables": tables})
        return {"step_id": step_id, "status": "dry_run", "planned_tables": tables}

    elimination_path = level_dir / "elimination.json"
    run_state_path = level_dir / "run_state.json"
    artifacts: Dict[str, Any] = {"elimination": str(elimination_path),
                                 "run_state": str(run_state_path),
                                 "scheduler_ledger": str(level_dir / "scheduler-ledger.json")}
    actual_tables = 0.0
    if elimination_path.is_file():
        elimination = json.loads(elimination_path.read_text(encoding="utf-8"))
        cumulative = float((elimination.get("ledger") or {}).get("spent_tables") or 0)
        actual_tables = max(0.0, cumulative - spent_before)
    problems: List[str] = []
    if actual_tables > tables + 1e-9:
        problems.append("调度器实际扣款 {0} 桌 > 本模块预留 {1} 桌（预算超支）".format(
            actual_tables, tables))
    if run_state_path.is_file():
        recorded = json.loads(run_state_path.read_text(encoding="utf-8"))
        levels = recorded.get("levels") or []
        recorded_roots = levels[0].get("root_keys") if levels else None
        planned_roots = [item["scenario_id"] for item in panel["root_specs"]]
        if recorded_roots and list(recorded_roots) != planned_roots:
            problems.append("实跑根组与计划面板不一致（计划 {0}，实际 {1}）".format(
                planned_roots[:3], list(recorded_roots)[:3]))
    ctx.ledger.settle(reservation, status="ok" if run.ok and not problems else "failed",
                      actual={"tables": actual_tables, "wall_clock_sec": run.elapsed_sec},
                      note="调度器退出码 {0}；实际扣款 {1} 桌".format(run.returncode, actual_tables))
    if actual_tables < tables and entries:
        ctx.archive.note(entries[0]["key"],
                         "{0}：预留 {1} 桌、实际 {2} 桌；差额因调度器拒绝了部分候选"
                         "（未执行即不计费）".format(level, tables, actual_tables))
    results = _read_level_results(elimination_path, level)
    # status 必须进 payload：调用方（cmd_run）据此判断"这一级有没有可用结果"，
    # 只在日志里写状态会让上层拿到一个永远"成功"的返回。
    payload = {"step_id": step_id, "level": level, "panel_id": panel["panel_id"],
               "planned_tables": tables, "actual_tables": actual_tables,
               "status": "ok" if run.ok and not problems else "failed",
               "problems": problems, "tool": run.to_json(), "artifacts": artifacts,
               "results": results}
    for entry in entries:
        record = ctx.archive.upsert(entry["key"], candidate=entry.get("candidate"),
                                    identity=entry.get("identity") or entry["key"],
                                    weights=dict(entry.get("weights") or {}))
        stats = results.get(record.identity)
        if stats is None:
            record.levels[level] = {
                "panel_id": panel["panel_id"], "roots": panel["roots"], "seats": panel["seats"],
                "status": "no_result",
                "reason": "本轮没有产出该候选的结果（调度器拒绝或运行失败）"}
            continue
        description = describe_statistics(stats)
        record.levels[level] = {
            "panel_id": panel["panel_id"], "root_set_id": panel.get("root_set_id"),
            "roots": panel["roots"], "seats": panel["seats"],
            "root_keys": [item["scenario_id"] for item in panel["root_specs"]],
            "statistics": dict(stats), "classification": description,
            "status": stats.get("status") or "ok"}
    ctx.state.mark(step_id)
    ctx.save()
    ctx.log(dict(payload))
    return payload


def step_promote(ctx: SearchContext, *, level: str, entries: Sequence[Mapping[str, Any]],
                 hypotheses: Mapping[str, str]) -> Dict[str, Any]:
    """冻结名额 + 探索名额（**运行前冻结**）。

    - 主名额：按根级点估计保留靠前者（复用调度器的 select_survivors，口径一致）；
    - 探索名额：留给“本面板未分辨但**有文字机制假设**”的候选；
      **没有填写机制假设就不占名额**（不臆造理由来凑数）；
    - 失败与不可排序的候选一律不晋级（缺失值不补零）。
    """

    sched = _sibling("sitin_scheduler")
    stats_map: Dict[str, Mapping[str, Any]] = {}
    by_identity = {str(entry["identity"] or entry["key"]): entry for entry in entries}
    for entry in entries:
        record = ctx.archive.records.get(entry["key"])
        level_data = (record.levels.get(level) if record else None) or {}
        stats = level_data.get("statistics")
        if stats:
            stats_map[str(entry["identity"] or entry["key"])] = stats
    keep_fraction = float(ctx.freeze.stop_rules["keep_fraction"])
    slots = int(ctx.freeze.stop_rules["exploration_slots"])
    survivors = sched.select_survivors(stats_map, keep_fraction)
    promoted = [by_identity[identity] for identity in survivors if identity in by_identity]
    unresolved, eliminated = [], []
    for entry in entries:
        identity = str(entry["identity"] or entry["key"])
        if identity in survivors:
            continue
        record = ctx.archive.records.get(entry["key"])
        level_data = (record.levels.get(level) if record else None) or {}
        description = level_data.get("classification") or {}
        stats = stats_map.get(identity) or {}
        if stats.get("status") == "failed":
            eliminated.append({"key": entry["key"], "identity": identity,
                               "reason": "本轮运行失败：不参与排序，也不补零"})
        elif description.get("state") == "unresolved":
            unresolved.append({"key": entry["key"], "identity": identity,
                               "reason": description.get("reason")})
        else:
            eliminated.append({"key": entry["key"], "identity": identity,
                               "reason": "开发面板点估计靠后（**开发期预算分配，不是统计结论**）"})
    exploration: List[Dict[str, Any]] = []
    for item in sorted(unresolved, key=lambda row: row["key"]):
        if len(exploration) >= slots:
            break
        hypothesis = (hypotheses or {}).get(item["key"])
        if not hypothesis:
            hypothesis = (hypotheses or {}).get(by_identity[item["identity"]].get("candidate") or "")
        if not hypothesis or not str(hypothesis).strip():
            continue
        exploration.append({"key": item["key"], "identity": item["identity"],
                            "reason": item["reason"], "hypothesis": str(hypothesis).strip()})
    payload = {"step_id": "promote:{0}".format(level), "level": level,
               "keep_fraction": keep_fraction, "exploration_slots": slots,
               "promoted": [entry["key"] for entry in promoted],
               "exploration": exploration, "unresolved": unresolved,
               "eliminated": eliminated}
    if ctx.dry_run:
        # dry-run 只演示口径，**不落结论也不标完成**：否则正式运行会把这一级
        # 当成"已完成"直接复用，晋级就被悄悄跳过了。
        ctx.log(dict(payload, status="dry_run"))
        return dict(payload, status="dry_run")
    for entry in promoted:
        ctx.archive.upsert(entry["key"], verdict="promoted",
                           verdict_reason="开发面板点估计靠前（冻结留存比例 {0}）".format(keep_fraction))
    for item in exploration:
        ctx.archive.upsert(item["key"], verdict="promoted_exploration",
                           verdict_reason="探索名额：本面板未分辨，机制假设已登记——{0}".format(
                               item["hypothesis"]))
    for item in unresolved:
        record = ctx.archive.records.get(item["key"])
        if record and record.verdict == "pending":
            ctx.archive.upsert(item["key"], verdict="unresolved",
                               verdict_reason="本面板未分辨；未进探索名额 ⇒ 如实标未分辨")
    for item in eliminated:
        record = ctx.archive.records.get(item["key"])
        if record and record.verdict == "pending":
            ctx.archive.upsert(item["key"], verdict="eliminated", verdict_reason=item["reason"])
    ctx.state.mark(payload["step_id"])
    ctx.save()
    ctx.log(dict(payload, status="ok"))
    return payload


#: 阶段命令模板的默认值（**冻结文件可覆盖**）。
#:
#: 为什么不把阶段 CLI 硬编码在代码里：阶段工具的候选进场接口仍在演进
#: （3.4 阶段比较的候选槽由同波次的另一包在 sitin_stage.py 中扩展）。
#: 硬编码一份就会在对方改参数名时**静默跑错命令**；模板放进冻结文件后，
#: “用哪条命令跑阶段比较”与预算、面板、停止规则一样，是运行前冻结、可复核的决定。
DEFAULT_STAGE_PROBE_COMMAND: Tuple[str, ...] = (
    "{python}", "{tools_dir}/sitin_stage.py", "check", "--panel-policy", "{candidate}",
    "--frozen-at", "2026-09-15")
DEFAULT_STAGE_COMMAND: Tuple[str, ...] = (
    "{python}", "{tools_dir}/sitin_stage.py", "run", "--contract-file", "{contract_file}",
    "--out", "{out}", "--participants", "{participants}")


def format_command(template: Sequence[str], values: Mapping[str, Any]) -> List[str]:
    """把冻结的命令模板渲染成 argv（只做命名占位符替换，不做 shell 展开）。"""

    rendered: List[str] = []
    for token in template:
        text = str(token)
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        rendered.append(text)
    return rendered


def stage_seating_probe(ctx: SearchContext, *, candidate_policy: str,
                        stage_plan: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """探针：阶段面板能不能坐进这个候选？

    阶段编排面板默认只允许**冻结稳定策略白名单**（sitin_stage.PANEL_POLICY_NAMES），
    候选启发式（adj.* 参数表达的调整）不在其中；同波次的另一包正在把“候选槽”加进
    阶段工具。本函数**不臆断**，而是按冻结模板实际探一次，把原始输出与退出码留作证据：

      - supported：工具接受该策略名（含候选槽已落地且模板已冻结的情形）；
      - unsupported：工具显式拒绝（白名单外）⇒ 记缺口，**不消耗阶段桌数预算**；
      - unknown：探针自身失败（工具缺失/语法错误/异常）⇒ 同样不消耗预算，按不可用处理。

    工具模块 import 失败（例如正在被编辑）**不得让探针抛异常**：那会让一次正常的
    “能力不可用”变成整轮崩掉，预算账目也没机会落盘。
    """

    stage_error: Optional[str] = None
    whitelist: Tuple[str, ...] = ()
    try:
        stage = _sibling("sitin_stage")
        whitelist = tuple(getattr(stage, "PANEL_POLICY_NAMES", ()))
    except Exception as exc:                        # noqa: BLE001 —— 探针失败按不可用处理
        stage_error = "{0}: {1}".format(type(exc).__name__, exc)
    frozen = (ctx.freeze.stage if isinstance(ctx.freeze.stage, Mapping) else {}) or {}
    template = ((stage_plan or {}).get("probe_command") or frozen.get("probe_command")
                or DEFAULT_STAGE_PROBE_COMMAND)
    # **两层判定**（STAGE-COMPARE-CONTRACT.md §2）：
    #   ① 冻结了执行件模板 ⇒ 探"执行件能力"（compare --help 是否接受候选与准入记录）；
    #   ② 未冻结模板 ⇒ 退回"阶段面板白名单"探针（旧路径，候选名必被拒）。
    capability_mode = bool(frozen.get("command_template") or (stage_plan or {}).get("command_template"))
    command = format_command(template, {
        "python": tool_python(), "tools_dir": TOOLS_DIR, "candidate": candidate_policy,
        "out": ctx.out, "contract_file": (stage_plan or {}).get("contract_file", "")})
    run = run_tool("sitin_stage.probe", command, cwd=ctx.out, timeout_sec=60.0,
                   dry_run=ctx.dry_run)
    help_text = "{0}\n{1}".format(run.stdout or "", run.stderr or "")
    if ctx.dry_run:
        verdict = "unknown"
    elif capability_mode and run.returncode == 0 and "--candidate" in help_text \
            and "--gate-record" in help_text:
        verdict = "supported"
    elif candidate_policy in whitelist:
        verdict = "supported"
    elif stage_error is not None or run.returncode is None:
        verdict = "unknown"
    elif "invalid choice" in (run.stderr or "") or run.returncode != 0:
        verdict = "unsupported"
    else:
        verdict = "unknown"
    return {"candidate_policy": candidate_policy, "whitelist": list(whitelist),
            "verdict": verdict, "capability_mode": capability_mode,
            "stage_module_error": stage_error,
            "command_template": list(template), "tool": run.to_json()}


def step_stage(ctx: SearchContext, *, entries: Sequence[Mapping[str, Any]],
               stage_plan: Mapping[str, Any]) -> Dict[str, Any]:
    """阶段比较：**先探能力，再决定要不要预留**；不支持就不花一分钱，如实记缺口。"""

    step_id = "stage:compare"
    probe = stage_seating_probe(
        ctx, candidate_policy=str(stage_plan.get("candidate_policy") or "candidate"),
        stage_plan=stage_plan)
    payload: Dict[str, Any] = {"step_id": step_id, "probe": probe,
                               "planned_pairs": int(stage_plan.get("pairs", 0)),
                               "entries": [entry["key"] for entry in entries]}
    if probe["verdict"] != "supported":
        payload.update({
            "status": "gap",
            "reason": ("阶段面板不接受候选策略名 {0!r}（判定 {1}；白名单 {2}）："
                       "**阶段桌数预算未动用**，缺口如实上报").format(
                           probe["candidate_policy"], probe["verdict"], probe["whitelist"]),
            "spent": {"tables": 0},
        })
        for entry in entries:
            ctx.archive.upsert(entry["key"], stage={
                "status": "gap", "reason": payload["reason"],
                "probe_command": probe["tool"]["command"]})
        ctx.state.mark(step_id)
        ctx.save()
        ctx.log(dict(payload, status="gap"))
        return payload
    # **预留与执行件上限用同一个数**（Lead 裁定 2026-09-15）：每会话桌数取**上界**
    # （含加赛；冻结文件 `tables_per_run_upper`）。曾经的"编排者按期望 9、执行件按上界 12"
    # 是两套数，必然再次相撞（本轮第 10 个场景就是这样被执行件判 budget_exhausted 丢掉的）。
    # 纪律是"消耗不可核对时保守预留"：**预留也保守，结算按实测**。
    upper = int(stage_plan.get("tables_per_run_upper") or stage_plan["tables_per_run"])
    per_arm = int(stage_plan["pairs"]) * upper * int(stage_plan["arms"])
    tables = per_arm * len(entries)
    if ctx.step_will_reuse(step_id):
        return ctx.step(step_id, account=ACCOUNT_SEARCH, amounts={}, note="阶段比较（复用）")
    wall_estimate = tables * ctx.wall_seconds_per_table() * WALL_SAFETY_FACTOR
    plan = ctx.step(step_id, account=ACCOUNT_SEARCH,
                    amounts={"tables": tables, "wall_clock_sec": wall_estimate},
                    note="阶段比较：{0} 臂 × {1} 对 × {2} 桌 × {3} 臂".format(
                        len(entries), stage_plan["pairs"], stage_plan["tables_per_run"],
                        stage_plan["arms"]))
    if plan["status"] == "reused":
        return plan
    reservation = plan["reservation"]
    stage_dir = ctx.out / "stage"
    stage_dir.mkdir(parents=True, exist_ok=True)
    template = (stage_plan.get("command_template")
                or (ctx.freeze.stage.get("command_template")
                    if isinstance(ctx.freeze.stage, Mapping) else None)
                or DEFAULT_STAGE_COMMAND)
    # **墙钟与预留同源**（Lead 裁定）：执行件的 --budget-wall-sec 就是本步预留里那条
    # 墙钟估算，不再有第三个数字（曾经契约 853.875 / 冻结 5400 / 实际 1250.62 三处不同）。
    arm_wall_budget = int(per_arm * ctx.wall_seconds_per_table() * WALL_SAFETY_FACTOR)
    # 执行件的 --budget-tables 与预留同源（都是上界）。
    arm_table_cap = int(stage_plan.get("tables_cap_per_arm") or per_arm)
    cell = _sibling("sitin_scheduler").cell_dir_name
    arms: List[Dict[str, Any]] = []
    spent_tables = 0.0
    recovered_wall_sec = 0.0
    problems: List[str] = []
    for entry in entries:
        arm_dir = stage_dir / cell(str(entry["key"]))
        arm_dir.mkdir(parents=True, exist_ok=True)
        # **恢复不重跑**：该臂的报告已经在盘上（上一次执行完但没来得及结算），
        # 直接读它对账，而不是再花一遍桌数（PLAN §6.2：先清理失联旧任务，
        # 不把"没写 done"解释成"从未执行"）。
        existing, _ = _read_stage_compare_report(arm_dir)
        if existing is not None and not ctx.allow_rerun:
            recovered_spent = _stage_tables_spent(existing)
            # 墙钟也要照实结转：报告里的 wall_sec 是执行件实测的墙上时钟秒。
            # 恢复路径不重跑，因此这一步的墙钟**不会**出现在 run_tool 的 elapsed 里——
            # 只按"恢复 = 0 秒"记账会把真实消耗藏起来（第一次恢复时正是这么记的，
            # 已在 README 与 run-stage/RECONCILE-NOTE.json 里如实披露）。
            recovered_wall = existing.get("wall_sec")
            if isinstance(recovered_wall, (int, float)) and not isinstance(recovered_wall, bool):
                recovered_wall_sec += float(recovered_wall)
            # 恢复路径同样要**消费溯源字段**：报告是不是可信的，与它是新跑还是恢复无关。
            provenance = stage_provenance(existing)
            recovered_status = existing.get("status") or "complete"
            if provenance["source_changed_during_run"] is True:
                problems.append(
                    "{0}：恢复时读到执行件报告声明**运行中源码被改** ⇒ 该报告不作结论依据".format(
                        entry["key"]))
                recovered_status = "untrusted_source"
            elif not provenance["compliant"]:
                problems.append("{0}：恢复时读到**非合规报告**，缺溯源字段 {1}".format(
                    entry["key"], provenance["missing_fields"]))
            arm = {"key": entry["key"], "status": recovered_status,
                   "recovered": True, "report": str(arm_dir / STAGE_COMPARE_REPORT),
                   "tables_spent": recovered_spent, "wall_sec": recovered_wall,
                   "metrics": existing.get("metrics"),
                   "panel": existing.get("panel"),
                   "verification": existing.get("verification"),
                   "provenance": provenance,
                   "contract_compliance": {"compliant": provenance["compliant"],
                                           "missing_fields": provenance["missing_fields"]}}
            if recovered_spent is None:
                problems.append("{0}：恢复时报告缺少 tables.spent，按预留 {1} 桌保守计费".format(
                    entry["key"], per_arm))
                spent_tables += per_arm
            else:
                spent_tables += recovered_spent
            arms.append(arm)
            ctx.archive.upsert(entry["key"], stage={
                "status": arm["status"], "tables_spent": recovered_spent,
                "metrics": arm.get("metrics"), "panel": arm.get("panel"),
                "verification": arm.get("verification"), "recovered": True,
                "provenance": arm.get("provenance"),
                "contract_compliance": arm.get("contract_compliance"),
                "report": arm["report"]})
            ctx.log({"step_id": step_id, "status": "arm_recovered", "key": entry["key"],
                     "tables_spent": recovered_spent})
            continue
        command: List[Any] = format_command(template, {
            "python": tool_python(), "tools_dir": TOOLS_DIR, "out": arm_dir,
            "contract_file": str(resolve_path(stage_plan["contract_file"]))
            if stage_plan.get("contract_file") else "",
            "participants": int(stage_plan["participants"]),
            "pairs": int(stage_plan["pairs"]), "arms": int(stage_plan["arms"]),
            "tables_per_run": int(stage_plan["tables_per_run"]),
            # 执行件的墙钟上限是**停止条件**而不是预留：给足（默认 3 倍估算），
            # 否则满机竞争下执行件会自己到点停下，白花已跑的桌数。
            "budget_tables": arm_table_cap,
            "budget_wall_sec": arm_wall_budget,
            "scenarios": int(stage_plan["pairs"]), "seed_base": int(stage_plan.get("seed_base", 0)),
            "focal": stage_plan.get("focal", ""),
            "candidate": entry.get("candidate"), "key": entry["key"],
            "weights": json.dumps(entry.get("weights") or {}, ensure_ascii=False),
            "gate_record": str(resolve_path(entry.get("gate_record"))
                               if entry.get("gate_record") else ""),
            "admission_corpus": str(resolve_path(stage_plan.get("admission_corpus")))
            if stage_plan.get("admission_corpus") else ""})
        run = run_tool("sitin_stage.compare", command, cwd=ctx.out,
                       timeout_sec=float(arm_wall_budget) + 600.0,
                       dry_run=ctx.dry_run)
        if ctx.dry_run:
            arms.append({"key": entry["key"], "status": "dry_run", "tool": run.to_json()})
            continue
        report, report_problem = _read_stage_compare_report(arm_dir)
        arm: Dict[str, Any] = {"key": entry["key"], "tool": run.to_json(),
                               "report": str(arm_dir / STAGE_COMPARE_REPORT)}
        if report is None:
            # 对不上账就**按预留额保守计费**：不免费重演，也不把缺口藏起来。
            problems.append("{0}：{1}（按预留 {2} 桌保守计费）".format(
                entry["key"], report_problem, per_arm))
            spent_tables += per_arm
            arm.update({"status": "unreconciled", "reason": report_problem,
                        "tables_charged": per_arm})
        else:
            # **溯源字段消费端**（契约 §3.5 / F1）：报告可不可信，先看这五个字段。
            provenance = stage_provenance(report)
            arm["provenance"] = provenance
            arm["contract_compliance"] = {
                "compliant": provenance["compliant"],
                "missing_fields": provenance["missing_fields"],
            }
            if provenance["source_changed_during_run"] is True:
                # 运行中源码被改 ⇒ 报告不可作结论依据；桌是真的跑过了，仍按实报结算。
                problems.append(
                    "{0}：执行件报告声明**运行中源码被改**（source_digest {1} → {2}）⇒ "
                    "该报告不作结论依据，候选标不受信".format(
                        entry["key"], str(provenance["source_digest_at_start"])[:12],
                        str(provenance["source_digest_at_end"])[:12]))
            elif not provenance["compliant"]:
                # 缺字段不等于造假：可能只是字段落地之前的产物——但**必须机器可区分**。
                problems.append("{0}：**非合规报告**，缺溯源字段 {1}".format(
                    entry["key"], provenance["missing_fields"]))
            spent = _stage_tables_spent(report)
            if spent is None:
                problems.append("{0}：报告缺少 tables.spent（对账唯一字段），按预留 {1} 桌保守计费".format(
                    entry["key"], per_arm))
                spent_tables += per_arm
                arm.update({"status": "unreconciled", "reason": "缺少 tables.spent",
                            "tables_charged": per_arm})
            else:
                spent_tables += spent
                status = report.get("status") or "complete"
                if provenance["source_changed_during_run"] is True:
                    status = "untrusted_source"
                elif not provenance["compliant"]:
                    status = status + "+noncompliant" if status == "complete" else status
                arm.update({"status": status,
                            "tables_spent": spent, "tables_planned": (report.get("tables") or {}).get("planned"),
                            "metrics": report.get("metrics"), "panel": report.get("panel"),
                            "verification": report.get("verification")})
        if not run.ok and arm.get("status") not in ("unreconciled",):
            arm["status"] = "unreconciled" if run.timed_out else (arm.get("status") or "failed")
            problems.append("{0}：执行件退出码 {1}".format(entry["key"], run.returncode))
        arms.append(arm)
        ctx.archive.upsert(entry["key"], stage={
            "status": arm.get("status", "unknown"),
            "tables_spent": arm.get("tables_spent"),
            "metrics": arm.get("metrics"), "panel": arm.get("panel"),
            "verification": arm.get("verification"),
            "reason": arm.get("reason"),
            # 溯源与合规结论进档案：下游只读机器字段时也能看出"这份报告可不可信"。
            "provenance": arm.get("provenance"),
            "contract_compliance": arm.get("contract_compliance"),
            "report": arm.get("report"), "command": list(run.command)})
    if ctx.dry_run:
        ctx.ledger.release(reservation, reason="dry-run：只做计划，不执行阶段比较")
        payload.update({"status": "dry_run", "arms": arms})
        ctx.log(dict(payload, status="dry_run"))
        return payload
    if spent_tables > tables + 1e-9:
        problems.append("执行件实报 {0} 桌 > 本模块预留 {1} 桌（预算超支）".format(
            spent_tables, tables))
    ctx.ledger.settle(reservation,
                      status="ok" if not problems else "failed",
                      actual={"tables": spent_tables, "wall_clock_sec": recovered_wall_sec + sum(
                          float((arm.get("tool") or {}).get("elapsed_sec") or 0.0)
                          for arm in arms)},
                      note="阶段比较：实报 {0} 桌 / 预留 {1} 桌".format(spent_tables, tables))
    payload.update({"status": "ran" if not problems else "failed", "arms": arms,
                    "planned_tables": tables, "actual_tables": spent_tables,
                    "problems": problems})
    ctx.state.mark(step_id)
    ctx.save()
    ctx.log(dict(payload))
    return payload


# ============================================================ 9. 计划核算与冻结交接

def compute_plan(freeze: Freeze, *, available: int) -> Dict[str, Any]:
    """按 PLAN-REVISION §6.1 的公式核算本批规模。

        T_L1  = C × K × S × 2
        C_max = floor((搜索桌数 − 固定成本 − 升级/阶段/重试预留) / (K × S × 2))

    **先扣预留，再算能跑几个候选**：反过来的话，“升级/阶段/重试”就会在预算耗尽时
    被悄悄砍掉——而那正是“到预算即停”要防的事。
    """

    panel = freeze.panel
    per_candidate = int(panel["roots"]) * int(panel["seats"]) * 2
    upgrade = freeze.upgrade
    upgrade_tables = (int(upgrade["slots"]) * int(upgrade["roots"])
                      * int(upgrade["seats"]) * 2)
    stage = freeze.stage
    stage_tables = int(stage["pairs"]) * int(stage["tables_per_run"]) * int(stage["arms"])
    retry = freeze.retry_reserve_tables
    search_tables = int(freeze.limit(ACCOUNT_SEARCH, "tables"))
    fixed = upgrade_tables + stage_tables + retry
    c_max = max(0, (search_tables - fixed) // per_candidate) if per_candidate else 0
    planned = min(c_max, int(available))
    return {
        "schema": PLAN_SCHEMA,
        "freeze_path": str(freeze.path), "freeze_sha256": freeze.sha256,
        "search_account": freeze.limits_of(ACCOUNT_SEARCH),
        "confirm_account": freeze.limits_of(ACCOUNT_CONFIRM),
        "panel": dict(panel), "upgrade": dict(upgrade), "stage": dict(stage),
        "arithmetic": {
            "per_candidate_tables": per_candidate,
            "upgrade_tables": upgrade_tables,
            "stage_tables": stage_tables,
            "retry_reserve_tables": retry,
            "fixed_reserve_tables": fixed,
            "search_tables": search_tables,
            "c_max_by_budget": int(c_max),
            "candidates_available": int(available),
            "candidates_planned": int(planned),
            "t_l1_tables": planned * per_candidate,
            "total_planned_tables": planned * per_candidate + fixed,
            "unallocated_tables": search_tables - planned * per_candidate - fixed,
        },
        "stop_rules": dict(freeze.stop_rules),
        "note": ("预留口径：升级/阶段/重试先在计划里扣住，L1 只用剩余；"
                 "确认账在本轮不可动用。"),
    }


def build_feedback(record: Mapping[str, Any], *, hypothesis: str = "") -> str:
    """三段反馈（PLAN §3.2）：**事实 / 相关表现 / 机制假设**分开，确认信息不出现。

    - 事实：解析、静态扫描、隔离装载、门禁结论都是本工具实测的；
    - 相关表现：开发面板根级统计（含 MDE 与“未分辨”标记），不含任何确认集信息；
    - 机制假设：**留给人填**；不填就明说没填，不由工具编一个。
    """

    gate = record.get("gate") or {}
    facts = [
        "准入核验：{0}{1}".format(
            gate.get("status"),
            "（{0}）".format(gate.get("reason")) if gate.get("reason") else ""),
        "候选身份：{0}".format(record.get("identity")),
    ]
    performance: List[str] = []
    for level, payload in sorted((record.get("levels") or {}).items()):
        stats = (payload or {}).get("statistics") or {}
        description = (payload or {}).get("classification") or {}
        performance.append(
            "{0}：根数 {1}，点估计 {2}，根级 SE {3}，MDE {4}，判定 {5}".format(
                level, stats.get("n_roots"), stats.get("mean"), stats.get("se_root"),
                stats.get("mde"), description.get("state")))
    if not performance:
        performance.append("（本轮没有可用的开发面板结果：未评估或未产出结果）")
    lines = ["## 事实（本工具实测）"] + ["- " + item for item in facts]
    lines += ["", "## 相关表现（开发面板，非确认证据）"] + ["- " + item for item in performance]
    lines += ["", "## 机制假设（人填；未填写即视为无）"]
    lines.append("- " + (hypothesis.strip() if hypothesis.strip()
                         else "（未填写：不由工具臆造机制假设）"))
    return "\n".join(lines) + "\n"


def load_for_report(out: Path, freeze_of: Optional[Freeze] = None,
                    legacy_wall_basis: Optional[str] = None) -> SearchContext:
    """**只读汇总**用的上下文：不校验冻结摘要，也不用于执行。

    为什么允许不校验：交接报告要把多本账（各自冻结、各自 sha）并列汇总，而执行路径
    的摘要校验一个字都不能松。这里只读、不预留、不结算，账本原样列出。
    """

    out = Path(out)
    freeze = freeze_of or Freeze.load(Path(_freeze_path_of(out)))
    ctx = SearchContext(out=out, freeze=freeze,
                        ledger=SearchLedger.load_for_report(out / "ledger.json", freeze),
                        archive=Archive.load_for_report(out / "archive.json"),
                        state=RunState.load(out / "state.json"),
                        steps_path=out / "steps.jsonl", dry_run=True,
                        legacy_wall_basis=legacy_wall_basis)
    return ctx


def _freeze_path_of(out: Path) -> str:
    """从产物目录里的 run 记录反查冻结文件路径；找不到就让调用方显式给。"""

    marker = Path(out) / "freeze-path.txt"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()
    raise ValueError("汇总外部产物目录需要 {0}/freeze-path.txt（写入本次执行的 --freeze 路径）".format(out))


def merge_records(contexts: Sequence[SearchContext], *, primary_sha: Optional[str] = None
                  ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按候选键合并多轮档案：**按 (等级, 面板身份) 合并**，跨面板不覆盖、只并列。

    为什么不能按等级名直接覆盖（组合评审 P1）：冒烟账与主账都有 "L1"，但那是**两块不同
    面板**（2 根 vs 16 根）。直接 `levels.update()` 会让冒烟的 L1 顶掉主账的 L1，
    交接件于是把冒烟数字当成了正式初筛结果——这是**报告失真**而不是缺字段。

    合并规则：
      - 主视图 `levels[level]` 只接受**与主冻结同 sha** 的上下文（`primary_sha`）；
        同等级同面板只出现一次，面板不同则进 `levels_other_panels`；
      - `verdict`/`verdict_reason` 同样只接受主冻结上下文的结论（否则冒烟的
        "留存比例 1.0 + 全部 promoted" 会把主账的"探索名额"结论顶掉）；
      - 返回 (合并后的记录, 跨面板冲突清单)，冲突由调用方记为 gap。

    边界：这不是"更严格"，而是唯一正确的算法——不同面板的均值不可直接比较（PLAN §5.1）。
    """

    merged: Dict[str, Dict[str, Any]] = {}
    conflicts: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for ctx in contexts:
        same_freeze = primary_sha is None or ctx.ledger.freeze_sha256 == primary_sha
        for key, record in ctx.archive.records.items():
            payload = record.to_json()
            payload["_source_out"] = str(ctx.out)
            payload["_same_freeze"] = same_freeze
            if key not in merged:
                merged[key] = {"key": key, "candidate": payload.get("candidate"),
                               "identity": payload.get("identity"),
                               "weights": dict(payload.get("weights") or {}),
                               "source": dict(payload.get("source") or {}),
                               "registration": payload.get("registration"),
                               "gate": dict(payload.get("gate") or {}),
                               "levels": {}, "levels_other_panels": [], "stage": {},
                               "verdict": "pending", "verdict_reason": "", "notes": []}
            target = merged[key]
            for level, level_payload in (payload.get("levels") or {}).items():
                panel_id = (level_payload or {}).get("panel_id")
                current = target["levels"].get(level)
                if current is None or (not same_freeze and current.get("_same_freeze") is False):
                    if same_freeze or current is None:
                        entry = dict(level_payload)
                        # **分类在汇总时按统计重算**：分类是统计量的纯函数，而档案里的
                        # 那份可能是旧版代码写的（本轮新增 no_observed_difference 后，
                        # 七对候选 L2x 的"均值 0/sd 0"就从"未分辨"变成"零差异观测"）。
                        # 重算保证交接件与当前口径一致，也不改档案里的历史事实。
                        if isinstance(entry.get("statistics"), Mapping):
                            entry["classification"] = describe_statistics(entry["statistics"])
                        entry["_same_freeze"] = same_freeze
                        entry["_source_out"] = payload["_source_out"]
                        target["levels"][level] = entry
                        continue
                if (current or {}).get("panel_id") == panel_id:
                    continue
                # 同等级、**不同面板**：不覆盖，并行留档 + 记冲突
                target["levels_other_panels"].append({
                    "level": level, "panel_id": panel_id,
                    "source_out": payload["_source_out"],
                    "same_freeze": same_freeze,
                    "statistics": (level_payload or {}).get("statistics"),
                    "classification": (level_payload or {}).get("classification")})
                conflicts.setdefault((key, level), []).append({
                    "panel_id": panel_id, "source_out": payload["_source_out"]})
            if (payload.get("stage") or {}).get("status"):
                target["stage"] = payload["stage"]
            if same_freeze and payload.get("verdict") and payload["verdict"] != "pending":
                target["verdict"] = payload["verdict"]
                target["verdict_reason"] = payload.get("verdict_reason") or ""
            target["notes"] = list(target.get("notes") or []) + list(payload.get("notes") or [])
    for key, level in sorted(conflicts):
        merged[key].setdefault("cross_panel_conflicts", []).append({
            "level": level,
            "panels": sorted({item["panel_id"] for item in conflicts[(key, level)]}),
            "note": "同一等级出现多块面板：主视图只保留主冻结那份，其余并列在 "
                    "levels_other_panels；**跨面板均值不可直接比较**"})
    return [merged[key] for key in sorted(merged)], [
        {"kind": "cross_panel_level_conflict", "candidate": key, "level": level,
         "panels": sorted({item["panel_id"] for item in items}),
         "sources": sorted({item["source_out"] for item in items}),
         "impact": "同一等级存在多块面板：交接件只把主冻结那份当正式结果，其余并列留档；"
                   "跨面板数字不得当同一批证据使用",
         "action": "若要合并比较，须先对齐面板（同根组/同换座）或按预登记规则取共同完整根组"}
        for (key, level), items in sorted(conflicts.items())]


def _stage_panels_source(contexts: Sequence[SearchContext]) -> Dict[str, Any]:
    """哪一本账的阶段段是"实际用过"的（有阶段预留且有实结桌数）。"""

    for item in contexts:
        for reservation in item.ledger.reservations:
            if reservation["step_id"] == "stage:compare" and reservation["status"] == "settled" \
                    and float(reservation["charged"].get("tables") or 0) > 0:
                return {"out": str(item.out), "freeze_path": str(item.freeze.path),
                        "freeze_sha256": item.freeze.sha256,
                        "tables": reservation["charged"]["tables"]}
    return {"out": str(contexts[0].out), "freeze_path": str(contexts[0].freeze.path),
            "freeze_sha256": contexts[0].freeze.sha256, "tables": 0,
            "note": "没有任何一本账跑过阶段比较：下面这份 stage 段是主冻结里的声明，不是已执行配置"}


def _stage_account_limit(contexts: Sequence[SearchContext]) -> Optional[float]:
    """跑过阶段比较的那本账的**上限**（不是已用）。"""

    source = _stage_panels_source(contexts)
    for item in contexts:
        if str(item.out) == source["out"]:
            return float(item.freeze.limit(ACCOUNT_SEARCH, "tables"))
    return None


def _stage_panels_in_use(contexts: Sequence[SearchContext]) -> Mapping[str, Any]:
    """实际用过的那份 `stage` 段（找不到就退回主冻结的声明，并已在 stage_source 里标注）。"""

    source = _stage_panels_source(contexts)
    for item in contexts:
        if str(item.out) == source["out"]:
            return item.freeze.stage
    return contexts[0].freeze.stage


def _apply_stage_supersession(records: Sequence[Mapping[str, Any]],
                              stage_evidence: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """把"旧阶段结论已被取代"写进 `candidates[].stage` 的**机器字段**。

    规则（Lead 裁定 F3，二选一里取"标不可用 + 指针"并附取代指标）：
      - `stage.metrics = None`、`stage.metrics_status = "superseded"`；
      - `stage.superseded_by` 指向取代报告；
      - `stage.superseding` 带取代运行的指标，并明标 `label="外部运行、未追认"`、
        `recognized_in_search_ledger=false`；
      - 旧运行的 `tables_spent`/`status` 保留（消耗记录照留，取代的是结论）。
    """

    superseded = stage_evidence.get("superseded") or {}
    superseding = stage_evidence.get("superseding") or {}
    key = superseded.get("record_key")
    patched: List[Dict[str, Any]] = []
    for item in records:
        target = dict(item)
        if key and target.get("key") == key and isinstance(target.get("stage"), Mapping):
            stage = dict(target["stage"])
            stage["metrics"] = None
            stage["metrics_status"] = "superseded"
            stage["superseded_by"] = superseding.get("source")
            stage["superseded_reason"] = superseded.get("verdict")
            stage["superseding"] = {
                "label": "外部运行、未追认",
                "source": superseding.get("source"),
                "executor_version": superseding.get("executor_version"),
                "pairs": superseding.get("pairs"),
                "tables": superseding.get("tables"),
                "metrics": superseding.get("metrics"),
                "secondary": superseding.get("secondary"),
                "recognized_in_search_ledger": False,
            }
            target["stage"] = stage
        patched.append(target)
    return patched


def freeze_binding(contexts: Sequence[SearchContext]) -> List[Dict[str, Any]]:
    """逐本账核对"台账记的冻结摘要"与"当前冻结文件摘要"是否一致（A2）。

    为什么必须核对：冻结件被原地改写后，台账的 `freeze_sha256` 就与文件对不上了
    （本轮 stage v2 就是这样：执行后被追加了两行，复跑命令会被台账拒绝）。交接件若
    只报**当前文件** sha，就把这条断裂掩盖了——那正是"报告失真"。所以两者都列，
    不一致就记 gap。
    """

    rows: List[Dict[str, Any]] = []
    for item in contexts:
        recorded = item.ledger.freeze_sha256
        current = None
        path = Path(item.freeze.path)
        if path.is_file():
            current = sha256_text(path.read_text(encoding="utf-8"))
        rows.append({
            "out": str(item.out), "freeze_path": str(path),
            "ledger_recorded_sha256": recorded, "file_current_sha256": current,
            "bound": bool(current) and recorded == current,
        })
    return rows


def _evidence_strength_of(item: Mapping[str, Any]) -> str:
    """这条生成产物是模型产出还是管线演练：model / drill / unknown。

    **unknown 归到 model 一侧**（fail-closed）：判不出来时宁可继续要求人审注册，
    也不能因为"查不到"就把一条产物从待注册清单里放走。字段由 step_generate 与
    _enrich_generated_records 写入，取值只来自生成端的 is_model_output。
    """

    value = str((item.get("source") or {}).get("evidence_strength") or "unknown")
    return value if value in ("model", "drill") else "unknown"

def _refresh_gate_fields(ctx: SearchContext, records: Sequence[Dict[str, Any]], *,
                         gate_dirs: Any,
                         admission_corpus: Optional[Path]) -> List[Dict[str, Any]]:
    """按**当前**门禁记录重扫并修正**报告**里的 `gate` 字段；返回变化清单（供披露）。

    只动报告，不动 archive：档案是"它自己那次运行当时的快照"，历史事实不改写；
    重扫出来的结论带 `rescanned_by`，读者能分清来源。**变了什么必须逐条列出来**——
    静默修正与静默错误一样不可核。
    """

    dirs = as_gate_dirs(gate_dirs)
    if not dirs:
        return []
    rescanned = rescan_admission(ctx, records, gate_dirs=dirs, admission_corpus=admission_corpus)
    changed: List[Dict[str, Any]] = []
    for item in records:
        result = rescanned.get(str(item.get("candidate") or ""))
        if not result:
            continue
        before = dict(item.get("gate") or {})
        gate = dict(result)
        gate["rescanned_by"] = ("freeze --gate-records 按当前记录重扫；archive.json 保留运行当时的快照")
        item["gate"] = gate
        if item.get("registration") == "pending_registration" and gate.get("status") == "admitted":
            item["registration"] = "registered"
        # **verdict 必须跟着 gate 一起改**（评审 F1）：同一对象里 gate=admitted 而
        # verdict_reason 还写着「准入未通过：no_admission_record」，是在对下游说两件相反的事。
        # 旧理由不删——降级成 `verdict_reason_superseded` 并注明"运行当时快照"。
        previous_reason = str(item.get("verdict_reason") or "")
        has_level_results = any((level or {}).get("statistics")
                                for level in (item.get("levels") or {}).values())
        if gate.get("status") == "admitted":
            if not has_level_results and not str(item.get("verdict") or "").startswith("promoted"):
                item["verdict"] = "pending"
                # 措辞刻意**不含**"准入未通过"这五个字：下游可能做朴素子串检索，
                # 哪怕是否定句也会被读成矛盾（评审 F1 的同类问题）。
                item["verdict_reason"] = ("准入已通过；本批未产出开发面板结果（未进入队列或未配预算），"
                                          "与准入结论无关")
        else:
            item["verdict"] = "blocked"
            item["verdict_reason"] = "准入未通过：{0}".format(gate.get("status"))
        # R2：机器指针——读者/程序都能从"被更正的那条"回到**真实记录**与**旧值**，不必读散文。
        # F5：只有**真的变了**才叫 superseded；6 条里实际只有 1 条变了，字段名与取值都要说真话。
        item["gate_rescan_pointer"] = {
            "previous_gate_status": before.get("status"),
            "changed": before.get("status") != gate.get("status"),
            "record_paths": gate.get("record_paths"),
            "record_path": gate.get("record_path"),
            "rescanned_by": gate.get("rescanned_by"),
        }
        if previous_reason and previous_reason != str(item.get("verdict_reason") or ""):
            item["verdict_reason_superseded"] = (
                "{0}（运行当时快照；已被 freeze --gate-records 的准入重扫更正）".format(previous_reason))
        if before.get("status") != gate.get("status"):
            changed.append({"candidate": item.get("candidate"),
                            "before": before.get("status"), "after": gate.get("status"),
                            "record_paths": gate.get("record_paths")})
    return changed


#: 更正留痕文件名（与产物同目录；见 REPORT-CORRECTIONS.md）。
REPORT_CORRECTIONS_FILE = "REPORT-CORRECTIONS.json"


def _apply_report_corrections(path: Path) -> Dict[str, Any]:
    """按同目录的 REPORT-CORRECTIONS.json 更正产物字段；返回 {data, applied}。

    为什么支持它：产物一旦写出就不该被静默手改；但**已知错的机器字段也不能留在账上**。
    更正声明与产物同目录、逐条给出 before/after/理由，读取方（含人）能看出哪些值被改过。
    文件不存在即视为无需更正。
    """

    text = path.read_text(encoding="utf-8")
    data: Any = json.loads(text)
    corrections_path = path.parent / REPORT_CORRECTIONS_FILE
    result: Dict[str, Any] = {"data": data, "applied": 0, "applied_paths": [],
                              "skipped": [], "error": None, "source": None,
                              "rolled_back": False}

    def roll_back() -> Dict[str, Any]:
        """出错即**整体回退**（wv26 F1-a″）：守卫注释写的是"宁可一条不改"，就真的不许留半更正。

        旧写法在"好条目已改、坏条目随后异常"时返回 applied=1 且 error 非空，而调用方
        （throughput_environment）只要 error 非空之外的路径都会照用 data ⇒ 权威面可能是半更正数据。
        这里把 data 还原成**原始解析结果**，并把已改的路径挪进 discarded_applied_paths（不静默丢）。
        """

        result["data"] = json.loads(text)
        result["discarded_applied_paths"] = result["applied_paths"]
        result["applied"] = 0
        result["applied_paths"] = []
        result["rolled_back"] = True
        return result
    if not corrections_path.is_file():
        return result
    result["source"] = str(corrections_path)
    try:
        payload = json.loads(corrections_path.read_text(encoding="utf-8"))
    except Exception as exc:                    # noqa: BLE001 —— 读不动就**明说**，不静默
        result["error"] = "{0}: {1}".format(type(exc).__name__, exc)
        return result
    # **更正件顶层必须是对象**（wv24 F1-a′）：更正件是人手写的，写坏形状（顶层写成数组/字符串/数字）
    # 时旧代码在 payload.get 上抛 AttributeError 穿出 build_handoff，整条命令中止——"证据写坏"不该
    # 变成"工具崩了"。形状不符一律 error 返回（不猜形状、不部分应用）。
    if not isinstance(payload, Mapping):
        result["error"] = "更正件顶层不是对象（读到 {0}）：拒绝应用".format(type(payload).__name__)
        return result
    # **更正件只对声明的那个文件生效**（F1）：同目录会不断有新产物落地（按步报告等），
    # 旧更正件若"谁都改"，就会覆盖**未来写入的正确值**——那是伪造，不是更正。
    if str(payload.get("target") or "") != path.name:
        result["error"] = "target 不匹配（更正件声明 {0!r}，本次读的是 {1}）".format(
            payload.get("target"), path.name)
        return result
    # **制品谓词**（wv20 F1）：光比"当前值等于 before"不够——来源/写法变了以后，同一个 false
    # 可能是"真回退"的新事实，而不是"旧写法记错的那一次"。更正件必须钉住**它要更正的那一份制品**：
    # 声明 target_sha256，读盘先比哈希，不符即拒改（"目标不是被更正的那一份"）。
    # **没有 target_sha256 就不许应用**（fail-closed）：不钉住制品，就证明不了"当前这个 false
    # 是旧写法记错的那一次、还是"内核真的回退了"——后者必须原样留下。
    expected_sha = str(payload.get("target_sha256") or "")
    if not expected_sha:
        result["error"] = "更正件缺少 target_sha256：无法证明目标是同一份制品，拒绝应用所有更正条目"
        return result
    if expected_sha:
        actual_sha = sha256_text(path.read_text(encoding="utf-8"))
        if actual_sha != expected_sha:
            result["error"] = ("target_sha256 不符：声明 {0}，磁盘 {1} —— 目标不是被更正的那一份").format(
                expected_sha[:16], actual_sha[:16])
            return result
    # **条目清单必须真的是数组**（wv24 F1-a′）：corrections 写成对象时，旧代码迭代出的是字符串键，
    # 随后 item.get 抛 AttributeError；写成字符串时更糟——迭代出的是单个字符，可能"改中"某个单键字段。
    # 形状不符即 error 返回：宁可一条不改，也不按猜出来的形状动产物。
    raw_corrections = payload.get("corrections")
    if raw_corrections is None:
        raw_corrections = []
    if not isinstance(raw_corrections, list):
        result["error"] = "corrections 不是数组（读到 {0}）：拒绝应用".format(
            type(raw_corrections).__name__)
        return result
    for item in raw_corrections:
        # **非对象条目不得静默丢**（wv24 F1-a′）：记 skipped 并带原因，人读件上看得见"这条没生效"。
        if not isinstance(item, Mapping):
            result["skipped"].append({"path": "-", "why": "条目不是对象（读到 {0}）".format(
                type(item).__name__)})
            continue
        # **空/缺失 path 不得静默 continue**（wv24 F1-a′）：旧写法 applied=0、skipped=[]、error=None，
        # 读者看到"更正件已挂上"却什么也没发生——静默丢弃比报错更危险。path 只认键数组。
        raw_path = item.get("path")
        if not isinstance(raw_path, (list, tuple)):
            result["skipped"].append({"path": "-", "why": "path 不是键数组（读到 {0}）".format(
                type(raw_path).__name__)})
            continue
        keys = list(raw_path)
        if not keys:
            result["skipped"].append({"path": "-", "why": "path 为空"})
            continue
        label = ".".join(str(key) for key in keys)
        # **任何异常都不许穿出**（wv22 F1-a）：leaf 缺失、下标越界、类型不符都是"这份产物里
        # 没有那个字段"，而不是"工具崩了"。更正件的语义恰恰包含"补记缺失字段"（before: null），
        # 所以 leaf 缺失按 None 处理；越界/类型不符记 skipped；其它异常记 error 并停止应用。
        try:
            node: Any = data
            missing = False
            for key in keys[:-1]:
                if isinstance(node, list):
                    # 下标越界/键不是整数 ⇒ 当作"这条路径不存在"（skipped），**不抛异常**、
                    # 也不中止其余条目（wv22 F1-a）。
                    text_key = str(key)
                    if not text_key.lstrip("-").isdigit():
                        node = None
                    else:
                        try:
                            node = node[int(text_key)]
                        except IndexError:
                            node = None
                elif isinstance(node, Mapping):
                    node = node.get(key)
                else:
                    missing = True
                    break
                if node is None:
                    missing = True
                    break
            if missing or node is None:
                result["skipped"].append({"path": label, "why": "中间路径不存在"})
                continue
            if isinstance(node, list):
                index = keys[-1] if isinstance(keys[-1], int) else None
                if index is None or not str(keys[-1]).lstrip("-").isdigit():
                    result["skipped"].append({"path": label, "why": "叶子键与容器类型不符（列表）"})
                    continue
                index = int(keys[-1])
                if index >= len(node) or index < -len(node):
                    result["skipped"].append({"path": label, "why": "列表下标越界"})
                    continue
                current = node[index]
                existed = True
            elif isinstance(node, Mapping):
                # **区分"键不存在"与"键存在且为 null"**（wv24 低项②）：两者的当前值都是 None，
                # 但前者是**补记**（原产物根本没这个字段）、后者是**更正**。人读件要点明是哪一种。
                existed = keys[-1] in node
                current = node.get(keys[-1])
            else:
                result["skipped"].append({"path": label, "why": "容器类型不符"})
                continue
        except Exception as exc:                # noqa: BLE001 —— 更正件异常绝不允许穿出调用方
            result["error"] = "{0}: {1}（更正件条目 {2} 处理失败，已停止应用并整体回退）".format(
                type(exc).__name__, exc, label)
            roll_back()
            break
        # **只纠正"确实还是那个错值"的字段**：当前值已不等于 before ⇒ 产物是新的/对的，
        # 跳过并登记 skipped，绝不覆盖（否则内核真的回退时会被永久翻成 true）。
        if current != item.get("before"):
            result["skipped"].append({
                "path": ".".join(str(key) for key in keys),
                "why": "before 不匹配（当前 {0!r}，更正件记 {1!r}）".format(current,
                                                                        item.get("before"))})
            continue
        try:
            if isinstance(node, list):
                node[int(keys[-1])] = item.get("after")
            else:
                node[keys[-1]] = item.get("after")
        except Exception as exc:                # noqa: BLE001
            result["error"] = "{0}: {1}（写回失败，已停止应用并整体回退）".format(
                type(exc).__name__, exc)
            roll_back()
            break
        result["applied"] += 1
        # **被改字段的路径要留下来**（wv24 低项②）：只给一个 applied 计数，人读面上看不出
        # "权威面里哪个字段其实是补记/更正出来的"。kind 由"原产物有没有这个键"决定。
        result["applied_paths"].append({"path": label, "before": current,
                                        "after": item.get("after"),
                                        "kind": "更正" if existed else "补记"})
    return result


def _pre_kernel_references(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    """把"启用内核前的口径来源"读成指针数组（F3）：**指针 + 字段名**，不复制数值。

    为什么需要它：`pre_kernel_measurements` 为空**不等于**"没有旧值"——旧值散在冻结件、台账与
    stage_policy 里。把它们的**位置**列出来，读数的人才能自己核，而不是被"pre=[]"误导成"没有旧口径"。
    """

    refs: List[Dict[str, Any]] = []
    for path in paths:
        entry: Dict[str, Any] = {"source": str(path)}
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:                # noqa: BLE001
            entry["error"] = "{0}: {1}".format(type(exc).__name__, exc)
            refs.append(entry)
            continue
        evidence = (data.get("wall_basis_evidence") or {}) if isinstance(data, Mapping) else {}
        if evidence.get("pre_kernel_reference"):
            entry["field"] = "wall_basis_evidence.pre_kernel_reference"
            entry["value"] = evidence["pre_kernel_reference"]
            entry["note"] = "该冻结件把启用前的对照写在这里（**不得**当报价依据）"
        elif "wall_estimate_sec_per_table" in (data or {}):
            entry["field"] = "wall_estimate_sec_per_table"
            entry["value"] = data["wall_estimate_sec_per_table"]
            entry["note"] = ("该冻结件的墙钟基准；若它产生于 fail-closed 规则之前即为历史口径"
                             "（已作废，只能显式一次性处置）")
        else:
            entry["note"] = "未在该文件里找到可引用的口径字段"
        refs.append(entry)
    return refs


#: 后端 implementation 里表示"没有原生后端在跑"的字面量（大小写不敏感）：读到它们同样是
#: **证据缺失**，不能当作"启用前"。为什么单列：内核回退/未装时上游可能写 none/null/unknown，
#: 若按"非 python 即 post"处理，会把"不知道"报成"已启用内核"——正是要防的那种相反结论。
NO_NATIVE_IMPLEMENTATION_TOKENS = frozenset({"none", "null", "unknown"})


def _is_python_backend(raw: Any) -> bool:
    """实现名是不是"纯 Python 分组算法"这一支（含**真实存在的回退名** python_grouped）。

    为什么不能只比字符串 "python"（wv26 F2-新）：内核的 Python 支在 _standard.py 里
    IMPLEMENTATION = "python_grouped"（原生才是 "c_grouped"），全树的 manifest.json 记的也是这个
    字面量。只比 "python" 会把**真实的回退**判成 post——那正是"把未装内核读成已启用"这条线本身，
    而且是唯一真实存在的名字。所以凡 python / python_* 一律算 Python 支。
    """

    if not isinstance(raw, str):
        return False
    token = raw.strip().casefold()
    return token == "python" or token.startswith("python_")


def _backend_state(raw: Any) -> str:
    """把后端实现名判成三态口径：post（已启用内核）/ pre（启用前）/ unknown（证据不足）。

    判据只认**非空字符串**（wv22 F2-a 与 wv24 F2-a′）：非字符串（123 / true / list / dict）一律
    unknown，不做 str() 兜底；空串与纯空白同理——它们在磁盘上等价于"没写实现名"。真值守卫
    （wv20 的 implementation and implementation != "python"）曾挡住空串，换成 isinstance 后丢了
    这一层，于是空串被判成 post，而该行 implementation 又渲染成 null，报价面出现"post 臂但
    implementation=null"的自相矛盾行；这里把空串显式归入 unknown，两处口径重新一致。
    """

    if not isinstance(raw, str) or not raw.strip():
        return "unknown"
    token = raw.strip().casefold()
    # **python_* 也算启用前**（wv26 F2-新）：python_grouped 是运行时真实存在的回退实现名。
    if _is_python_backend(raw):
        return "pre"
    if token in NO_NATIVE_IMPLEMENTATION_TOKENS:
        return "unknown"
    return "post"


def _native_block_from_backend_info(info: Any, base: Optional[Mapping[str, Any]] = None
                                    ) -> Dict[str, Any]:
    """由 _standard.backend_info() 的结果构造 counters 的 native 块（写者侧唯一判据）。

    为什么抽出来（wv26 F2-新）：写者与读者必须用**同一个**三态判据。旧写法在写者侧单独写
    str(implementation) != "python"，于是真实的回退实现名 python_grouped 被写成 native_loaded=true，
    与自己同一行的 fallback_reason 自相矛盾；而现在两处都走 _backend_state，不可能各自漂移。
    post ⇒ true（原生在跑）；pre（含 python_grouped）⇒ false；判不出来 ⇒ null，不猜。
    """

    state = _backend_state(info.get("implementation")) if isinstance(info, Mapping) else "unknown"
    return dict(base or {}, backend=info,
                native_loaded=None if state == "unknown" else state == "post")


def _source_labels(path: Path) -> Dict[str, Any]:
    """从产物所在目录导出"这次跑叫什么、算在哪本账上"（wv24 低项①）。

    为什么每行都要带：同一次 --throughput-env 可以把多个运行目录一起挂上（例如把 4 桌的 v1 目录
    与 8 桌的 v2 目录并排挂上），而冻结件里的 account 只描述其中一次。行内不带来源时，读数的人
    会把两次运行的臂混成一锅。

    account 取同目录 ledger.json 里**实际被记账的账户**（reservations 的 account 去重）——这才是
    "这笔机时算在谁头上"；台账的 accounts 只是该次运行开着的账户（通常是 search+confirm 两个），
    拿它当行标签会给出每行都一样的常数。取不到才退回账户清单，再取不到就留 None，不猜。
    """

    labels: Dict[str, Any] = {"account": None, "account_basis": "none",
                              "run_label": path.parent.name}
    ledger = path.parent / "ledger.json"
    try:
        document = json.loads(ledger.read_text(encoding="utf-8"))
    except Exception:                           # noqa: BLE001 —— 没有台账只是缺标签，不影响读数
        return labels
    if not isinstance(document, Mapping):
        return labels
    charged = {str(row.get("account")) for row in (document.get("reservations") or [])
               if isinstance(row, Mapping) and row.get("account")}
    if charged:
        labels["account"] = "+".join(sorted(charged))
        labels["account_basis"] = "charged"
        return labels
    # **没有记账记录就不许把"开着的账户"写成 account**（wv26 低项①）：accounts 是这次运行开了哪些
    # 账户（通常是 search+confirm 两个），拿它当行标签会被读成"这笔机时记在谁头上"。这里 account 留
    # null，另给 account_basis="opened" 与 opened_accounts，读者自己判断。
    opened = document.get("accounts")
    if isinstance(opened, Mapping) and opened:
        labels["account_basis"] = "opened"
        labels["opened_accounts"] = sorted(str(name) for name in opened)
    return labels


def throughput_environment(sources: Sequence[Path],
                           pre_kernel_refs: Sequence[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    """交接件里的**机时口径环境**块：由产物读出，明确切开"启用内核前/后"两个口径。

    为什么必须机器可读（评审 R8）：本包已把历史常数作废、把内核回退定成成因，但**交接件里别处**
    的秒/桌仍混着两个口径（L1b/L2b 的 7.39/7.24 是启用前的数）。只靠散文说明，读者很容易把
    两个数当成同一个。这里把每条测量**按它自己的后端**分类，并给出报价规则。
    """

    rows: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []
    corrections_seen: List[Dict[str, Any]] = []
    for path in sources:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:                       # noqa: BLE001 —— 读不动就如实记下
            checks.append({"source": str(path), "error": "无法解析"})
            continue
        if isinstance(data, Mapping) and data.get("measurements"):
            # **已更正的产物**：同目录 REPORT-CORRECTIONS.json 声明"哪些字段是错的、改成什么、为什么"。
            # 这是本项目"已知错值必须更正并留痕"的机器可读形式——读数的人不会拿到旧值。
            corrected = _apply_report_corrections(Path(path))
            data = corrected["data"]
            # 更正动作**必须可见**（F5）：读不动 / 命中 0 条都不能静默。
            corrections_seen.append({"source": str(path), "corrections_file": corrected["source"],
                                     "applied": corrected["applied"],
                                     # **哪些字段被改过要说清**（wv24 低项②）：只给计数时，
                                     # 权威面自身看不出 implementation 其实是补记出来的值。
                                     "applied_paths": corrected["applied_paths"],
                                     # **错误面要能看出"改没改"**（wv26 F1-a″）：出错即整体回退，
                                     # 被丢弃的那几条改动员挪到 discarded_applied_paths，不静默丢。
                                     "rolled_back": corrected["rolled_back"],
                                     "discarded_applied_paths": corrected.get(
                                         "discarded_applied_paths") or [],
                                     "skipped": corrected["skipped"],
                                     "error": corrected["error"]})
            for item in data["measurements"]:
                # **类型守卫**（wv22 F2-b）：native/backend 不是映射时（如 native:"c_grouped"）
                # 旧代码会 AttributeError 穿出；这里一律当"没有后端块"⇒ unknown。
                native = item.get("native") if isinstance(item.get("native"), Mapping) else {}
                backend = (native.get("backend") if isinstance(native.get("backend"), Mapping)
                           else {})
                implementation_raw = backend.get("implementation")
                # **空串不准渲染成实现名**（wv24 F2-a′）：空白串在磁盘上等同于没写；值为 null 且
                # 该行 state=unknown，两处一致（旧写法会渲染 null 却判 post，自相矛盾）。
                implementation = (implementation_raw
                                  if isinstance(implementation_raw, str)
                                  and implementation_raw.strip() else None)
                rows.append({
                    "source": str(path), "arm": item.get("arm"), "tables": item.get("tables"),
                    # **来源账目/运行目录**（wv24 低项①）：多目录并挂时，读数的人要能分辨
                    # "这条臂是哪一次跑、算在哪本账上"。
                    **_source_labels(Path(path)),
                    "wall_seconds_per_table": item.get("wall_seconds_per_table"),
                    "cpu_seconds_per_table": item.get("cpu_seconds_per_table"),
                    "instructions_per_table": item.get("instructions_per_table"),
                    "implementation": implementation,
                    # **不参与口径判定的独立证据**（wv22 F2-c）：`native_loaded is True` 是可靠正证据，
                    # 不得静默丢弃，但也不能用它把口径"提升"——分类只由后端块决定（fail-closed）。
                    "native_loaded_observed": (native.get("native_loaded")
                                               if isinstance(native, Mapping) else None),
                    "native_loaded_note": "仅供人读：不参与口径判定",
                    "native_path": backend.get("native_path"),
                    "fallback_reason": backend.get("fallback_reason"),
                    "measured_at_utc": data.get("generated_at_utc"),
                    # **三态**（F2）：有后端块且非 python ⇒ post；显式 python ⇒ pre；
                    # 读不到/没有后端块 ⇒ **unknown**。"缺证据"绝不能翻成"启用前"这类相反结论。
                    # **只认后端块**（wv20 F2）：`native_loaded=false` 在没有后端块时既可能是"真回退"、
                    # 也可能是"当时没传 --native"——分不清就一律 unknown，绝不猜成相反的环境结论。
                    # 代价（可接受）：旧纯 Python 臂的旧记录变 unknown，这正是 fail-closed 该给的答案。
                    # **只认字符串形态的后端块**（wv22 F2-a）：非字符串的 implementation（123 / true）
                    # 一律 unknown，不做 str() 兜底——那会把"没证据"读成"post"。
                    # **空串/纯空白也归 unknown**（wv24 F2-a′）：判据收在 _backend_state 一处，
                    # 免得三态判定在别处又被写成"非 python 即 post"。
                    "backend_state": _backend_state(implementation_raw),
                })
        else:
            # 漏装检查（check_native_backend.py --json）等一次性环境报告：原样留档。
            checks.append({"source": str(path), "report": data})
    post = [row for row in rows if row["backend_state"] == "post"]
    pre = [row for row in rows if row["backend_state"] == "pre"]
    unknown = [row for row in rows if row["backend_state"] == "unknown"]
    rule = ("报价一律用 post_kernel_measurements 的口径，且**新冻结件必须声明实测的 wall_estimate_sec_per_table**；"
            "**post 为空 ⇒ 不得报价**，先跑 throughput-probe 并挂上产物；pre_kernel_measurements 与交接件别处"
            "（stage_policy 的吞吐句、freeze 的 pre_kernel_references）属**内核启用前**口径，**不得与新值混用**；"
            "unknown_backend_measurements 是**证据缺失**，既不当作启用前、也不当作启用后。")
    block: Dict[str, Any] = {
        "schema": "sitin-throughput-environment/1",
        "status": "measured" if rows else "unmeasured",
        "sources": [str(path) for path in sources],
        "post_kernel_measurements": post,
        "pre_kernel_measurements": pre,
        "unknown_backend_measurements": unknown,
        "pre_kernel_references": list(pre_kernel_refs),
        "corrections_applied": corrections_seen,
        "environment_checks": checks,
        "quote_rule": rule,
        "counts": {"post": len(post), "pre": len(pre), "unknown": len(unknown)},
    }
    if not rows:
        block["instruction"] = "本交接件没有挂任何机时口径产物：报价前先跑 throughput-probe，并用 --throughput-env 把报告挂上。"
    return block

def _sync_classifications(contexts: Sequence[SearchContext]) -> List[Dict[str, Any]]:
    """把**按当前口径重算**的等级判定**写回档案**，旧标签降级为分类快照。

    为什么要写回（评审 wv12 ③）：`merge_records` 早就在内存里重算 classification，但档案里
    还留着旧函数写下的标签 ⇒ **同一等级在两份产物里判定不同**（实测 `seven_pairs_path_value@L2x`：
    档案 `unresolved`、交接件 `no_observed_difference`，stats 完全相同）。两个机器字段互相不一致就是陷阱，
    所以这里写回，并保留 `classification_superseded`（"运行当时快照"）——**修正而不是抹掉历史**。
    """

    changed: List[Dict[str, Any]] = []
    for item in contexts:
        dirty = False
        for key, record in item.archive.records.items():
            for level, payload in (record.levels or {}).items():
                stats = (payload or {}).get("statistics")
                if not isinstance(stats, Mapping):
                    continue
                fresh = describe_statistics(stats)
                current = payload.get("classification")
                if current == fresh:
                    continue
                payload["classification_superseded"] = dict(current or {})
                payload["classification_superseded_note"] = (
                    "运行当时快照；已按当前口径重算并写回（同一 stats 在旧函数下会得到不同标签）")
                payload["classification"] = fresh
                changed.append({"out": str(item.out), "key": key, "level": level,
                                "before": (current or {}).get("state"),
                                "after": fresh.get("state")})
                dirty = True
        if dirty:
            item.archive.save()
            item.log({"step_id": "classification-sync", "status": "written-back",
                      "changed": [row for row in changed if row["out"] == str(item.out)]})
    return changed


def _record_origins(contexts: Sequence[SearchContext]) -> Dict[str, str]:
    """档案键 -> 该键所在产物目录。

    多本账并列时同一个键可能出现在多本账里：这里按 contexts 顺序**先出现者优先**，
    与 merge_records 的主视图规则一致（汇总只认主冻结那份）。
    """

    origins: Dict[str, str] = {}
    for ctx in contexts:
        for key in ctx.archive.records:
            origins.setdefault(key, str(ctx.out))
    return origins


def _enrich_generated_records(records: Sequence[Dict[str, Any]],
                              origins: Mapping[str, str]) -> List[Dict[str, Any]]:
    """给生成产物档案补齐**源码指纹**与**取证强度**，并登记补了什么（不覆盖已有值）。

    这两件都是"只有到交接时才暴露"的静默缺失：

      ① source.code_sha256 为空。早期版本把生成端的**相对** attempt_dir 按本进程工作目录解析，
         文件当然找不到，指纹于是被记成 null——空指纹既证明不了"产物没被换过"，
         也证明不了"没越界"。这里按
         <产物目录>/generate/<request_id>/<attempt_dir>/candidate.py 就地重算。
      ② source.evidence_strength 缺失。老档案没有这个字段；读一次生成端的 records.jsonl
         就能判定它是模型产出还是管线演练。判定逻辑只在 generation_evidence_strength 里，
         这里不复制第二套。

    只补不覆盖：字段已有值时原样保留（历史事实不改写）。补过的项逐条进
    handoff 的 generated_evidence_backfill，读者能看出哪些值是交接时算出来的。
    """

    backfilled: List[Dict[str, Any]] = []
    for item in records:
        source = item.get("source") or {}
        if source.get("kind") != "generated_attempt":
            continue
        out = origins.get(item["key"])
        base = (Path(out) / "generate" / str(source.get("request_id") or "")) if out else None
        if base is None or not base.is_dir():
            base = None
        changed: Dict[str, Any] = {}
        if not source.get("code_sha256") and base is not None:
            fingerprint = _code_sha_of(source.get("attempt_dir"), base=base)
            if fingerprint:
                source["code_sha256"] = fingerprint
                source["code_sha256_backfill"] = (
                    "交接汇总时按 <产物目录>/generate/<request_id>/<attempt_dir>/candidate.py"
                    " 重算：早期版本以本进程工作目录为基准，故原值为 null")
                changed["code_sha256"] = fingerprint
        if not source.get("evidence_strength"):
            strength = (generation_evidence_strength(base, item["key"]) if base is not None
                        else {"strength": "unknown", "evidence_kind": None,
                              "is_model_output": None, "admission_eligible": None})
            source["evidence_strength"] = strength["strength"]
            if source.get("evidence_kind") is None:
                source["evidence_kind"] = strength.get("evidence_kind")
            if source.get("is_model_output") is None:
                source["is_model_output"] = strength.get("is_model_output")
            if source.get("admission_eligible") is None:
                source["admission_eligible"] = strength.get("admission_eligible")
            changed["evidence_strength"] = strength["strength"]
            changed["evidence_kind"] = strength.get("evidence_kind")
            changed["evidence_is_model_output"] = strength.get("is_model_output")
        item["source"] = source
        if changed:
            backfilled.append(dict(changed, key=item["key"], source_out=out))
    return backfilled

def build_handoff(ctx: SearchContext, *, pool: Mapping[str, Any],
                  extra_gaps: Sequence[Mapping[str, Any]] = (),
                  extra: Sequence[SearchContext] = (),
                  development_spend: Optional[Mapping[str, Any]] = None,
                  stage_evidence: Optional[Mapping[str, Any]] = None,
                  gate_dirs: Any = None,
                  admission_corpus: Optional[Path] = None,
                  legacy_wall_basis: Optional[str] = None,
                  throughput_env: Sequence[Path] = (),
                  pre_kernel_references: Sequence[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    """3.5 冻结与交接：**三种完成状态分开报**，缺口单列，开发结果不冒充确认。

    `extra`：额外产物目录（各自冻结、各自账本）。多轮执行时不合并台账（那会破坏
    "一本账一个冻结摘要"），而是**并列列出**并在 totals 里求和。
    """

    contexts = [ctx] + list(extra)
    # **先写回重算的等级判定，再合并**（wv12 ③）：否则档案与交接件会对同一等级给出不同标签。
    classification_sync = _sync_classifications(contexts)
    records, cross_panel = merge_records(contexts, primary_sha=ctx.ledger.freeze_sha256)
    # 生成产物的两件机器可核事实（源码指纹、取证强度）在汇总时就地补齐：
    # 早期版本写下的 null 指纹与"夹具被当成待注册候选"都不能带进 3.5 交接件。
    backfill = _enrich_generated_records(records, _record_origins(contexts))
    # **报告侧**的准入重扫：门禁记录可能出现在别处（如后续包补跑的），
    # 档案里的 gate 只代表它自己那次运行；不重扫就会让机器字段对下游说假话。
    gate_rescan_changes = _refresh_gate_fields(ctx, records, gate_dirs=gate_dirs,
                                               admission_corpus=admission_corpus)
    # **墙钟基准必须来自实测声明**（Lead 裁定 F2）：汇总时逐本账核一遍——缺字段的旧冻结件
    # 只有在调用方**显式点名**（--legacy-wall-basis）时才允许继续，且必须进交接件，不许静默。
    wall_basis_rows: List[Dict[str, Any]] = []
    plain_missing: List[str] = []
    for item in contexts:
        try:
            # **走 ctx 级取基准**（评审 F11）：冻结件级调用不记录，于是 --legacy-wall-basis
            # 的"文件级留痕"在 freeze 路径上根本不存在（全仓 0 命中）。ctx 级会写
            # <out>/wall-basis-declarations.jsonl 并进 steps.jsonl——一次性处置必须可核。
            item.legacy_wall_basis = legacy_wall_basis if legacy_wall_basis is not None \
                else getattr(item, "legacy_wall_basis", None)
            basis = item.wall_basis(item.freeze)
        except WallBasisMissing as error:
            plain_missing.append(str(item.freeze.path))
            basis = {"source": "missing", "reason": str(error), "seconds_per_table": None}
        wall_basis_rows.append(dict(basis, out=str(item.out)))
    if plain_missing:
        raise SystemExit(
            "以下冻结件未声明 {0}，且未给 --legacy-wall-basis：{1}；"
            "**不得静默回落历史常数**（已作废）。要么在本件里声明实测值，要么显式声明一次性处置。"
            .format(WALL_BASIS_FIELD, "；".join(plain_missing)))
    # **取代关系必须落到机器字段**（Lead 裁定 F3）：下游只读 `candidates[].stage`，
    # 光在 narrative 里说"已取代"不算数。被取代的旧指标一律置空 + 指针，另附取代运行的指标
    # 并明标"外部运行、未追认"。
    if stage_evidence:
        records = _apply_stage_supersession(records, stage_evidence)
    candidates = [item for item in records if item.get("registration") == "registered"]
    screened = [item for item in candidates
                if any((level or {}).get("statistics")
                       for level in (item.get("levels") or {}).values())]
    promoted = [item for item in candidates if str(item.get("verdict", "")).startswith("promoted")]
    unresolved = [item for item in candidates if item.get("verdict") == "unresolved"]
    pending = [item for item in records if item.get("registration") == "pending_registration"]

    # 数据驱动的几个量（评审 F3/F9）：未分辨清单、本账实测秒/桌、诊断账——全部由数据算，
    # 不写死（"三个候选""7.9 秒/桌""288 桌"都曾写死过，随后与同一文件的其它数字打架）。
    def _state_rows(states: Any) -> List[Tuple[str, str, str]]:
        return [(str(item.get("candidate") or item["key"]), level,
                 str(((payload or {}).get("classification") or {}).get("state")))
                for item in records
                for level, payload in (item.get("levels") or {}).items()
                if str(((payload or {}).get("classification") or {}).get("state")) in states]

    # 三态**分开取**：把 resolved_negative 和"未分辨"混成一个集合，会让结论句比数据弱一档
    # （评审 F10：档案里明明记着"方向可分辨（负）"，结论句却说"无一可分辨"）。
    unresolved_rows = _state_rows(("unresolved", "no_observed_difference"))
    positive_rows = _state_rows(("resolved_positive",))
    negative_rows = _state_rows(("resolved_negative",))
    measured_spt, measured_tables, measured_wall = measured_wall_throughput(ctx.ledger)
    diagnostic_accounts = list((development_spend or {}).get("diagnostic_accounts") or [])
    diagnostic_tables = sum(float(item.get("tables") or 0) for item in diagnostic_accounts)

    gaps: List[Dict[str, Any]] = [dict(item) for item in extra_gaps]
    # **"待注册"与"演练产物"必须分开报**（本轮残余证据收口）：两者在档案里长得一样
    # （都跑完解析与隔离装载），但处置完全相反——一个要人审后注册，一个按合同**不得**注册。
    # 判据取自生成端自己写下的 is_model_output，本模块不推断；读不到按待注册保守处理。
    pending_model = [item for item in pending
                     if _evidence_strength_of(item) != "drill"]
    pending_drill = [item for item in pending
                     if _evidence_strength_of(item) == "drill"]
    if pending_model:
        gaps.append({
            "kind": "pending_registration",
            "count": len(pending_model),
            "items": sorted(item["key"] for item in pending_model),
            "evidence_strength": "model（真模型产出）或 unknown（读不到台账，按待注册保守处理）",
            # 计数与桌数**由数据渲染**（评审 F3/F9）：写死"三个候选 / 288 桌"必然随批次失真。
            "impact": "**模型产出**的生成产物停在待人工静态注册：门禁与调度都按注册名查找，"
                      "未注册即装载失败，**这些产物本轮不可能进入效果评估**。"
                      "这与「评估预算用不出去」是两件事——本账已结算评估步 {0:g} 桌，"
                      "用在了 {1} 个已注册候选上，并未被本缺口卡住；本缺口卡住的是这些新产物。"
                      .format(measured_tables, len(candidates)),
            "action": "人审 → 在 src/hangma_bot/policy/heuristics/ 增模块并在 "
                      "CANDIDATE_FACTORIES 加一行 → 跑 G-1/G-2/G-3 → 重新核验绑定身份后入队"
                      "（本模块不做注册，也不改 policy 源码）",
        })
    if pending_drill:
        gaps.append({
            "kind": "drill_not_registrable",
            "count": len(pending_drill),
            "items": sorted(item["key"] for item in pending_drill),
            "evidence_kind": sorted({str((item.get("source") or {}).get("evidence_kind"))
                                     for item in pending_drill}),
            "impact": "生成管线的**演练产物**（is_model_output=false，如 replay / "
                      "origin=format_fixture）：它们跑完了解析与隔离装载，但**不是模型产出**。"
                      "按合同（新增模块 + 注册表一行 + 人工审核）它们**不得**静态注册——"
                      "把夹具注册进候选表，等于让手工代码冒充生成候选，后续所有桌赛结果都会"
                      "挂在一个没有生成来源的身份上。**这不是评估阻塞项，也不消耗任何预算**。",
            "action": "无需注册：保留为管线证据即可；真实模型产出的注册诉求见 pending_registration",
        })
    # **阶段缺失的真实原因**（组合评审：不得张冠李戴）：不是"面板坐不进候选"
    # （那条缺口在执行件 ver 2 + 契约 v1.1 之后已经不成立），而是**本批阶段名额只有 1 个**
    # （180 桌按 MDE≈6.3 分定），其余候选根本没配阶段预算。
    stage_gaps = [item for item in records
                  if (item.get("stage") or {}).get("status") in ("gap", None)
                  and not (item.get("stage") or {}).get("tables_spent")]
    stage_gaps = [item for item in stage_gaps if item.get("registration") == "registered"
                  and (item.get("gate") or {}).get("status") == "admitted"]
    if stage_gaps:
        stage_ran = sorted(item["key"] for item in candidates
                           if (item.get("stage") or {}).get("tables_spent"))
        gaps.append({
            "kind": "candidate_without_stage_budget",
            "count": len(stage_gaps),
            "items": sorted(item.get("key") for item in stage_gaps),
            "stage_ran": stage_ran,
            "supersedes": ["candidate_without_stage_evidence"],
            "impact": "这些准入候选**未配阶段预算**（本批阶段名额 = floor(180 / (10 × 12 × 2)) = 1，"
                      "只给了开发面板评分序第 1 的候选）：因此它们**没有阶段主指标证据**，"
                      "不得用开发面板结果代替，最终选择只能输出桌赛开发候选集",
            "action": "阶段名额按'想分辨多少分'配发（MDE≈6.3 分需 180 桌/候选；"
                      "MDE≈5 需 ~288 桌、MDE≈2.5 需 ~1134 桌）；扩阶段预算需显式授权",
        })
    if stage_evidence:
        superseded = stage_evidence.get("superseded") or {}
        gaps.append({
            "kind": "stage_evidence_superseded",
            "out": superseded.get("out"),
            "pairs": superseded.get("pairs"),
            "tables_spent": superseded.get("tables_spent"),
            "superseded_by": (stage_evidence.get("superseding") or {}).get("source"),
            "impact": "旧阶段运行的部分场景因**配对键选错被误废**，其结论（unrankable）不再代表"
                      "当前执行件；已由同面板的 ver 3 运行取代。**两边的桌数都留在账上**，"
                      "取代的是结论，不是消耗记录",
            "action": "后续阶段比较一律用执行件 ver 3 及以后的报告；旧产物保留为历史证据",
        })
    legacy_rows = [row for row in wall_basis_rows if row.get("source") == "legacy-declared"]
    if legacy_rows:
        gaps.append({
            "kind": "wall_basis_legacy_exception",
            "count": len(legacy_rows),
            "items": [row.get("freeze_path") for row in legacy_rows],
            "seconds_per_table": legacy_rows[0].get("seconds_per_table"),
            "reason": legacy_rows[0].get("reason"),
            "impact": "**已披露例外**：这些冻结件产生于 fail-closed 规则生效之前，墙钟基准是**历史值**"
                      "（非实测），由操作者**显式点名**后才允许继续。历史常数已作废，本条的作用就是"
                      "让后人分清「某次墙钟超限是实测报错，还是这个回退踩出来的」。",
            "action": "新冻结件必须声明实测的 wall_estimate_sec_per_table；本条的旧件只在复现历史运行时出现",
        })
    if cross_panel:
        gaps.extend(cross_panel)
    binding = freeze_binding(contexts)
    broken = [row for row in binding if not row["bound"]]
    if broken:
        gaps.append({
            "kind": "freeze_binding_broken",
            "count": len(broken),
            "items": [row["freeze_path"] for row in broken],
            "impact": "台账记录的冻结摘要与当前冻结文件不一致：**该账的复跑命令会被台账拒绝**"
                      "（执行路径校验摘要，这是有意的），交接件不得只报当前文件 sha 掩盖它",
            "action": "保留执行用的那一版冻结件（台账原值），把改动另存为**新版本文件**；"
                      "确需在同目录续跑，则换新 --out 并重新冻结",
        })
    unknown_calls = ctx.ledger.unknown_token_calls(ACCOUNT_SEARCH)
    if unknown_calls:
        gaps.append({
            "kind": "token_usage_unknown",
            "count": unknown_calls,
            "impact": "{0} 次生成的输出 token 用量读不到：已按**预留额保守计入**"
                      "搜索账（估 {1} token），并单独计数；不得当作 0 消耗".format(
                          unknown_calls, ctx.ledger.unknown_token_charged(ACCOUNT_SEARCH)),
            "action": "按生成端产物补齐 usage（headless 通道从会话日志的 usage 事件累加）；"
                      "补齐前按未知次数上限约束，不用未知量扩预算",
        })
    # 三条口径的分子都在这里算一次：预算执行口径取自各本账的**结算后**余额，
    # 开发期消耗只从登记文件读（**不追认**），两者**不合并**成一个"合计"。
    search_spent_tables = sum(item.ledger.spent(ACCOUNT_SEARCH)["tables"]
                              for item in contexts)
    search_remaining_tables = sum(item.ledger.remaining(ACCOUNT_SEARCH)["tables"]
                                  for item in contexts)
    search_limit_tables = sum(item.ledger.limits[ACCOUNT_SEARCH]["tables"]
                              for item in contexts)
    development_tables = ((development_spend or {}).get("totals") or {}).get("tables")

    unspent = ctx.ledger.remaining(ACCOUNT_SEARCH)
    if unspent.get("tables", 0) > 0:
        gaps.append({
            "kind": "unspent_search_budget",
            "impact": "搜索桌数未用尽（剩余 {0} 桌）".format(unspent["tables"]),
            "action": "按剩余预算扩样本或加候选；扩预算需显式授权（台账不自动扩容）",
        })

    return {
        "schema": HANDOFF_SCHEMA,
        "generated_at_utc": utc_now(),
        "freeze": {"path": str(ctx.freeze.path), "sha256": ctx.freeze.sha256},
        "completion_states": {
            COMPLETION_TOOL: {
                "status": "完成",
                "evidence": ["tools/sitin_search.py", "tools/test_sitin_search.py",
                             str(ctx.steps_path), str(ctx.ledger.path)],
                "scope": "串联生成/门禁/评估/阶段四段并分账记账（阶段比较已按 STAGE-COMPARE-CONTRACT v1.1 由执行件跑通并对账）",
            },
            COMPLETION_CANDIDATES: {
                "status": ("桌赛开发候选集（有候选晋级）" if promoted
                           else "无候选进入开发候选集"),
                "naming": "交付物是**桌赛开发候选集**；阶段主指标意义上本轮无选优，"
                          "不得命名为最终赛事最优候选",
                "screened": sorted(item["key"] for item in screened),
                "promoted": sorted(item["key"] for item in promoted),
                # 各级"未分辨"的候选：**开发面板分辨不出方向**（不是"没有区别"的证明）。
                "unresolved_at_level": sorted(
                    "{0}@{1}".format(item["key"], level)
                    for item in candidates
                    for level, payload in (item.get("levels") or {}).items()
                    if ((payload or {}).get("classification") or {}).get("state") == "unresolved"),
                "unresolved_without_promotion": sorted(item["key"] for item in unresolved),
            },
            COMPLETION_RELEASE_GATE: {
                "status": "未通过（本轮无候选进入发布门禁）",
                "reason": "缺少阶段主指标证据与独立确认；开发面板结果不构成发布依据",
            },
        },
        "candidates": candidates,
        "levels_other_panels": {item["key"]: item["levels_other_panels"] for item in records
                                if item.get("levels_other_panels")},
        # **"待注册"只放模型产出**（演练产物单列）：字段名即结论，不能把夹具混进来。
        "generated_pending_registration": [item["key"] for item in pending_model],
        "generated_not_registrable": [item["key"] for item in pending_drill],
        "generated_evidence_backfill": list(backfill),
        # 报告侧准入重扫的披露：读了哪些目录、哪几个候选的状态被修正。
        "gate_rescan": ({"dirs": [str(path) for path in as_gate_dirs(gate_dirs)],
                         "changed": list(gate_rescan_changes)} if as_gate_dirs(gate_dirs) else None),
        # **panels.stage 用实际跑过阶段比较的那份冻结**（组合评审 A7）：主冻结里的 stage 段
        # 是初筛那一版（pairs=4、面板白名单探针），拿它当"阶段面板"会把没跑过的配置写成已执行。
        "panels": {"frozen": dict(ctx.freeze.panel), "upgrade": dict(ctx.freeze.upgrade),
                   "stage": dict(_stage_panels_in_use(contexts)),
                   "stage_source": _stage_panels_source(contexts)},
        "freeze_binding": freeze_binding(contexts),
        "wall_basis": wall_basis_rows,
        "classification_sync": classification_sync,
        # R8：机时口径环境（post/pre kernel 分开）——"别让读者把两个口径当成同一个数"。
        "throughput_environment": throughput_environment(throughput_env,
                                                          pre_kernel_references),
        # R2：消费契约——**交接件是权威读数面**，档案是运行当时快照。
        "consumption_contract": {
            "authoritative": "handoff.json（本文件）",
            "archive_role": "archive.json 是**运行当时**的快照，但**不是**只读的：admission / verdict /"
                            "classification 会由 run 或 freeze 按当时口径重算后写回（见 classification_sync、"
                            "steps.jsonl 的 classification-sync 行）；被 --gate-records 重扫更正的条目只在"
                            "**本文件**更新，并带 gate_rescan_pointer 指回真实记录与旧值",
            "why": "重扫要读多处记录、还会跨账合并；若写回档案，快照就不再是快照。",
        },
        "development_spend": dict(development_spend) if development_spend else None,
        # **阶段证据链**：外部（执行件）运行可以**取代**我账本里那一次，但必须①标来源
        # ②标"旧运行 superseded"③按开发期消耗登记（不追认）。外部运行永远不进我的 spent。
        "stage_evidence": dict(stage_evidence) if stage_evidence else None,
        # **阶段名额的准入与报价口径**（Lead 裁定 2026-09-15 二）：不按"每个候选配一份"摊开——
        # 那样花 480 桌换来的仍是一句"分辨不出"，买不到结论。阶段比较只留给**先在开发面板上
        # 出现可分辨效应**的候选，届时按实测吞吐单独报价。
        "stage_policy": {
            # 条件句**收窄为正向可分辨**（评审 F10）：分类语义里 resolved_± 都算"方向可分辨"，
            # 但"达到晋级条件"指的是**正向**效应；负向可分辨同样要如实渲染（负结果也是结果）。
            "rule": "阶段比较名额只配给**在开发面板上已出现正向可分辨效应（resolved_positive）**的候选；"
                    "申请时按当时的实测吞吐单独报价（不由本模块自动扩预算）。"
                    "**措辞修订**：此处原写「已出现可分辨效应」，按分类语义 resolved_negative 也属方向可分辨，"
                    "口径易被读宽；现收窄为正向，负向单独列出且**不构成追加依据**",
            # **由数据渲染**（评审 F3）：候选数与"未分辨/零差异"的清单都从档案算，
            # 不再写死"三个候选"——同一份交接件里 promoted 已经列了 4 个，写死必然自相矛盾。
            "current": ("本轮达到该条件（正向可分辨）的等级：**{0}**；"
                        "未分辨或零差异观测 {1} 个等级（{2}）；"
                        "**方向可分辨但为负（不构成追加依据）{3} 个等级（{4}）**"
                        "⇒ 无正向可分辨效应，**阶段预算不追加**").format(
                            "、".join("{0}@{1}".format(row[0], row[1]) for row in positive_rows) or "无",
                            len(unresolved_rows),
                            "、".join("{0}@{1}={2}".format(*row) for row in unresolved_rows) or "无",
                            len(negative_rows),
                            "、".join("{0}@{1}={2}".format(*row) for row in negative_rows) or "无"),
            "resolved_positive_at_level": ["{0}@{1}".format(row[0], row[1]) for row in positive_rows],
            "resolved_negative_at_level": ["{0}@{1}".format(row[0], row[1]) for row in negative_rows],
            "stage_account": {
                "out": _stage_panels_source(contexts)["out"],
                # **上限**取自该账的冻结件，**已用**取自它的结算记录：两个数不能混成一个
                # （曾经把"已用 174"渲染成"上限 174"）。
                "limit_tables": _stage_account_limit(contexts),
                "spent_tables": _stage_panels_source(contexts)["tables"],
                "note": "现有阶段账保持不动，不再摊开给其他候选"},
            # 吞吐也**由数据渲染**：从本账已结算的评估步里算，不写死历史那个数。
            "throughput_note": (
                "本账已结算评估步实测 **{0:.2f} 秒/桌**（{1:g} 桌 / {2:.1f} 秒）；"
                "历史常数 {3:.5f} **已作废**（它在产生它的代码树上都不复现）。"
                "**墙钟不受 token 预算约束**，是真正的瓶颈").format(
                    measured_spt if measured_spt is not None else float("nan"),
                    measured_tables, measured_wall, LEGACY_SECONDS_PER_TABLE),
            "throughput_measured_seconds_per_table": measured_spt,
            # **口径标记**（F3）：这个数由本账**已结算**的评估步算出，而本账的表是**内核启用前**跑的
            # ⇒ 与 throughput_environment.post_kernel_measurements 不是同一个口径，必须标出来。
            "throughput_measured_calibre": "pre-kernel（本账已结算的评估步在内核启用前执行；不得与 post-kernel 值混用）",
            "naming": "**无正向可分辨候选**时，交付物是**桌赛开发候选集**（保留阶段相关变体），"
                      "**不得命名为最终赛事最优候选**",
        },
        # **三条账目口径各自有名字，互不相加**（Lead 裁定 2026-09-15）：
        #   ① 预算执行口径 = 各本搜索账的 spent/limit/remaining——「超限即停」的分母，唯一口径；
        #   ② 开发期消耗口径 = development_spend（登记不追认）：不进 spent、不进上限分母；
        #   ③ 机时总消耗 = ①+②，**非预算口径**：给总量时必须同时带三条限定语，
        #      否则会被读成「预算已花掉这么多」，直接污染超限判定的分母。
        "accounting_calibres": {
            "budget_execution": {
                "name": "预算执行口径",
                "definition": "六本搜索账的 spent / limit / remaining；这是「预算花了多少、还能花多少」的唯一口径，也是「超限即停」的分母",
                "spent_tables": search_spent_tables,
                "limit_tables": search_limit_tables,
                "remaining_tables": search_remaining_tables,
                "ledgers": len(contexts),
            },
            "development_spend": {
                "name": "开发期消耗口径",
                "definition": "development-spend.json 的逐项：登记不追认——不进任何搜索账的 spent，也不进任何上限的分母",
                "tables": development_tables,
            },
            "machine_time_total": {
                # 口径名收窄（评审 F6）：它只含"预算执行 + 开发期登记"，**不含**诊断账。
                "name": "机时总消耗（预算执行 + 开发期登记；**不含诊断账**）",
                "definition": ("= 预算执行口径 spent + 开发期消耗口径；**非预算口径**、**不进任何上限分母**、"
                               "**不可用作预算执行复算**；**另计** {0:g} 桌诊断账（{1}），诊断账既不是搜索账也不是确认账"
                               ).format(diagnostic_tables,
                                        "、".join("{0} {1:g}".format(item.get("account"),
                                                                     item.get("tables") or 0)
                                                  for item in diagnostic_accounts) or "无"),
                "tables": (search_spent_tables + development_tables
                           if development_tables is not None else None),
            },
            "why_not_one_number": "两组数字的钱不是同一笔：开发期消耗不从搜索预算里出；相加后再当预算执行数读，会让超限判定的分母漂掉",
        },
        "budget": {
            # 每本账各自带冻结摘要：**不合并台账**（一本账一个冻结摘要），只并列 + 求和。
            "ledgers": [{
                "out": str(item.out),
                "freeze_path": str(item.freeze.path),
                "freeze_sha256": item.freeze.sha256,
                "accounts": item.ledger.to_json()["accounts"],
            } for item in contexts],
            "totals": {
                "search_spent_tables": sum(item.ledger.spent(ACCOUNT_SEARCH)["tables"]
                                           for item in contexts),
                "search_remaining_tables": sum(item.ledger.remaining(ACCOUNT_SEARCH)["tables"]
                                               for item in contexts),
                "search_spent_calls": sum(item.ledger.spent(ACCOUNT_SEARCH)["calls"]
                                          for item in contexts),
                "search_unknown_token_calls": sum(item.ledger.unknown_token_calls(ACCOUNT_SEARCH)
                                                  for item in contexts),
            },
            "search_remaining": ctx.ledger.remaining(ACCOUNT_SEARCH),
            "confirm_remaining": ctx.ledger.remaining(ACCOUNT_CONFIRM),
            "confirm_touched": any(bool(item.ledger.spent(ACCOUNT_CONFIRM)["tables"]
                                        or item.ledger.reserved(ACCOUNT_CONFIRM)["tables"])
                                   for item in contexts),
            # 两个维度同时报：已知累计在 spent.output_tokens，未知次数单独计数。
            "token_usage_unknown_calls": unknown_calls,
            "token_usage_unknown_charged": ctx.ledger.unknown_token_charged(ACCOUNT_SEARCH),
        },
        "pool": {"candidates": [entry.get("candidate") for entry in pool.get("candidates", ())],
                 "generated": [item.get("attempt_dir") for item in pool.get("generated", ())]},
        "gaps": gaps,
        "next_stage": {
            "handoff_to": "第四阶段独立确认",
            "do_not_reuse": ["开发面板根级结果不得当确认证据",
                             "本模块的淘汰是**开发期预算分配规则**，不声称统计显著"],
            "required_before_confirm": [
                "候选冻结（身份 + 参数 + 源码指纹 + 准入记录）",
                "阶段主指标可算：执行件已支持候选槽（sitin_stage.py compare）；"
                "阶段预算须按**每会话上界**冻结（契约 v1.1）",
                "独立确认预算与面板另行冻结，且确认结果不回流本次搜索",
            ],
        },
    }


#: 进 Markdown 的缺口**定位字段**（键序即渲染顺序，label 是给读者看的中文名）。
#:
#: **为什么要有这张表**：缺口的机器字段（哪个候选、哪一级、哪块面板、哪本账）过去只进
#: handoff.json，不进 Markdown——于是三条**不同候选**的跨面板冲突在交接件里长得一模一样
#: （本轮实测症状），读者既看不出差异，也无从判断该去哪儿复核。定位信息必须和散文一起出现。
#:
#: items / reasons 不在此列：它们逐条成行，见 render_handoff_md 里的专门渲染。
_GAP_LOCATOR_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("candidate", "候选"),
    ("level", "等级"),
    ("count", "条数"),
    ("panels", "面板"),
    ("sources", "账本目录"),
    ("out", "产物目录"),
    ("freeze_path", "冻结文件"),
    ("tables_spent", "桌数"),
    ("pairs", "配对数"),
    ("stage_ran", "已跑阶段的候选"),
    ("superseded_by", "取代者"),
    ("evidence_kind", "取证来源"),
    ("evidence_strength", "取证强度"),
    ("step_id", "步"),
    ("axis", "超限维度"),
    ("seconds_per_table", "墙钟基准（秒/桌）"),
    ("reason", "原因"),
    ("reserved", "预留"),
    ("charged", "实结"),
)


def _correction_value_text(value: Any, kind: Any) -> str:
    """更正条目的取值渲染：用 **JSON 字面量**，不要走桌数格式化器。

    为什么单开一个（wv26 F3-新）：_tables_text() 把 bool 当"没有这个量"（它服务的是桌数），
    于是 native_loaded 那条被渲染成"更正（（原本没有该字段） → null）"——恰好把**更正**说成**补记**，
    与机器字段 before=false/after=true 矛盾。这里 before/after 一律按 JSON 渲染（false / true / null）。
    """

    if kind == "补记" and value is None:
        return "（原本没有该字段）"
    return json.dumps(value, ensure_ascii=False)


def _tables_text(value: Any, *, missing: str = "（未登记）") -> str:
    """桌数渲染：None 表示"没有这个量"，**不是 0**（0 与未知是两件事，不能混）。"""

    if value is None or isinstance(value, bool):
        return missing
    if isinstance(value, (int, float)):
        return "{0:g}".format(float(value))
    return str(value)


def _render_gap_value(value: Any) -> str:
    """定位字段的 Markdown 取值：列表用「、」连成一行，其余按 str 渲染。"""

    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value) or "（空）"
    return str(value)

def render_handoff_md(handoff: Mapping[str, Any]) -> str:
    states = handoff["completion_states"]
    lines = ["# 坐隐 3.4/3.5 冻结与交接", "",
             "生成时间（UTC 墙钟）：{0}".format(handoff["generated_at_utc"]), "",
             "## 三种完成状态（分开报）", "",
             "| 状态 | 结论 | 说明 |", "| --- | --- | --- |"]
    lines.append("| {0} | {1} | {2} |".format(
        COMPLETION_TOOL, states[COMPLETION_TOOL]["status"], states[COMPLETION_TOOL]["scope"]))
    lines.append("| {0} | {1} | 已初筛 {2}；晋级 {3}；**开发面板上未分辨 {4}**（{5}） |".format(
        COMPLETION_CANDIDATES, states[COMPLETION_CANDIDATES]["status"],
        len(states[COMPLETION_CANDIDATES]["screened"]),
        len(states[COMPLETION_CANDIDATES]["promoted"]),
        len(states[COMPLETION_CANDIDATES]["unresolved_at_level"]),
        "、".join(states[COMPLETION_CANDIDATES]["unresolved_at_level"]) or "无"))
    lines.append("| {0} | {1} | {2} |".format(
        COMPLETION_RELEASE_GATE, states[COMPLETION_RELEASE_GATE]["status"],
        states[COMPLETION_RELEASE_GATE]["reason"]))
    lines += ["", "## 候选（依赖 / 参数 / 覆盖 / 根级误差 / 阶段情景差）", "",
              "| 候选 | 绑定身份 | 准入 | 开发面板（根级） | 阶段情景差 | 结论 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for item in handoff["candidates"]:
        stats_cells = []
        for level, payload in sorted((item.get("levels") or {}).items()):
            stats = (payload or {}).get("statistics") or {}
            description = (payload or {}).get("classification") or {}
            if stats.get("n_roots") or description:
                stats_cells.append("{0}: n={1} 均值={2} SE={3} MDE={4} 判定={5}".format(
                    level, stats.get("n_roots"), stats.get("mean"), stats.get("se_root"),
                    stats.get("mde"), description.get("state")))
        stage = (item.get("stage") or {})
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            item.get("candidate") or item.get("key"),
            "`{0}`".format(item.get("identity")),
            (item.get("gate") or {}).get("status"),
            "<br>".join(stats_cells) or "（无）",
            stage.get("status") or "（未执行）",
            "{0}{1}{2}".format(
                item.get("verdict"),
                "：" + item.get("verdict_reason", "") if item.get("verdict_reason") else "",
                "（旧理由已被准入重扫更正，见 verdict_reason_superseded）"
                if item.get("verdict_reason_superseded") else "")))
    lines += ["", "## 预算（每本账各自一个冻结摘要）", "",
              "| 产物目录 | 冻结文件 | 搜索已用桌数 | 搜索剩余桌数 | 未知用量调用 |",
              "| --- | --- | ---: | ---: | ---: |"]
    for item in handoff["budget"]["ledgers"]:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            item["out"], item["freeze_path"],
            item["accounts"]["search"]["spent"]["tables"],
            item["accounts"]["search"]["remaining"]["tables"],
            item["accounts"]["search"]["unknown_token_calls"]))
    lines.append("| **合计（预算执行口径）** | — | **{0}** | **{1}** | **{2}** |".format(
        handoff["budget"]["totals"]["search_spent_tables"],
        handoff["budget"]["totals"]["search_remaining_tables"],
        handoff["budget"]["totals"]["search_unknown_token_calls"]))
    lines.append("")
    lines.append("- 确认账**未被任何一本账动用**：{0}".format(
        not handoff["budget"]["confirm_touched"]))
    lines.append("")
    # **三条口径各自有名字、互不相加**（Lead 裁定 2026-09-15）：人读件必须先把口径说清，
    # 否则"机时总消耗"会被读成"预算已花掉这么多"，超限判定的分母随之漂掉。
    calibres = handoff.get("accounting_calibres")
    if calibres:
        exec_side = calibres["budget_execution"]
        dev_side = calibres["development_spend"]
        machine_side = calibres["machine_time_total"]
        lines += ["", "## 三条账目口径（各自有名字，**互不相加**）", "",
                  "- **{0}**：{1}".format(exec_side["name"], exec_side["definition"]),
                  # 账本用浮点累加，渲染时去掉无意义的 .0；None 显式写成"未登记"而不是 0。
                  "  - 已用 **{0}** 桌 / 上限 {1} 桌 / 剩余 {2} 桌（{3} 本账并列）".format(
                      _tables_text(exec_side["spent_tables"]),
                      _tables_text(exec_side["limit_tables"]),
                      _tables_text(exec_side["remaining_tables"]), exec_side["ledgers"]),
                  "- **{0}**：{1}".format(dev_side["name"], dev_side["definition"]),
                  "  - 合计 **{0}** 桌（另 {1} token）".format(
                      _tables_text(dev_side["tables"]),
                      ((handoff.get("development_spend") or {}).get("totals") or {}).get(
                          "output_tokens")),
                  "- **{0}**：{1}".format(machine_side["name"], machine_side["definition"]),
                  "  - **{0}** 桌 = {1}（预算执行口径）+ {2}（开发期消耗口径）".format(
                      _tables_text(machine_side["tables"]),
                      _tables_text(exec_side["spent_tables"]),
                      _tables_text(dev_side["tables"])),
                  "- 为什么不合成一个数：{0}".format(calibres.get("why_not_one_number"))]
    develop = handoff.get("development_spend")
    if develop:
        lines += ["", "## 开发期消耗（登记，不追认）", "",
                  "> 这些是**开发期**已经发生的消耗（含同波次执行件与预检），只登记以便看清全貌；",
                  "> **不进搜索账的 spent，也不进任何上限的分母**——否则「超限即停」的分母含义就漂了。", ""]
        lines += ["| 项 | 数量 | 出处 | 可复跑 |", "| --- | ---: | --- | --- |"]
        for item in develop.get("items", []):
            lines.append("| {0} | {1} {2} | {3} | {4} |".format(
                item.get("label"), item.get("value"), item.get("unit", ""),
                item.get("source", ""), item.get("reproducible", "—")))
        totals = develop.get("totals") or {}
        if totals:
            # **不叫"任务级合计"**：这个名字会让人把它当预算执行数读（Lead 裁定 2026-09-15）。
            lines.append("| **{0}** | **{1} 桌 / {2} token** | — | 见逐项 |".format(
                develop.get("totals_label") or "开发期消耗合计（口径见上）",
                totals.get("tables"), totals.get("output_tokens")))
        for note in develop.get("notes", ()):
            lines.append("- {0}".format(note))
    evidence = handoff.get("stage_evidence")
    if evidence:
        superseded = evidence.get("superseded") or {}
        superseding = evidence.get("superseding") or {}
        metrics = superseding.get("metrics") or {}
        lines += ["", "## 阶段比较证据（取代关系）", "",
                  "- **决定**：{0}".format((evidence.get("decision") or {}).get("path", "-")),
                  "- **理由**：{0}".format((evidence.get("decision") or {}).get("reason", "-")),
                  "- **旧运行（superseded）**：{0}，{1} 桌，配对 {2}，状态 {3}".format(
                      superseded.get("out"), superseded.get("tables_spent"),
                      superseded.get("pairs"), superseded.get("status")),
                  "- **取代运行**：{0}（执行件 {1}），配对 {2}，桌数 spent {3} / planned {4}".format(
                      superseding.get("source"), superseding.get("executor_version"),
                      superseding.get("pairs"), (superseding.get("tables") or {}).get("spent"),
                      (superseding.get("tables") or {}).get("planned")),
                  "- **主指标**：Δ={0}，根级 sd={1}，SE={2}，**MDE={3}**（n={4} 场景）".format(
                      metrics.get("delta"), metrics.get("sd_root"), metrics.get("se_root"),
                      metrics.get("mde"), metrics.get("n_scenarios")),
                  "- **官方加赛**（只记录、不作废场景）：**{0} 条记录 / {1} 张桌**".format(
                      (superseding.get("extra_tables") or {}).get("records"),
                      (superseding.get("extra_tables") or {}).get("tables"))
                  + ("" if not (superseding.get("extra_tables") or {}).get("detail")
                     else "：{0}".format(json.dumps(
                         (superseding.get("extra_tables") or {}).get("detail"),
                         ensure_ascii=False))),
                  "- **结论**：**{0}**——{1}".format(
                      (evidence.get("conclusion") or {}).get("state"),
                      (evidence.get("conclusion") or {}).get("why")),
                  "- **措辞纪律**：{0}".format(
                      (evidence.get("conclusion") or {}).get("what_changed")),
                  "- **记账**：{0}".format(
                      (evidence.get("accounting") or {}).get("reason")
                      or (evidence.get("accounting") or {}).get("authorization")
                      or (evidence.get("accounting") or {}).get("registered_as"))]
    policy = handoff.get("stage_policy")
    if policy:
        lines += ["", "## 阶段名额口径（Lead 裁定）", "",
                  "- 规则：{0}".format(policy["rule"]),
                  "- 本轮：{0}".format(policy["current"]),
                  "- 阶段账：`{0}`（上限 {1} 桌 / 已用 {2} 桌）".format(
                      policy["stage_account"]["out"], policy["stage_account"]["limit_tables"],
                      policy["stage_account"]["spent_tables"]),
                  "- 吞吐：{0}".format(policy["throughput_note"]),
                  "- 命名：{0}".format(policy["naming"])]
    wall_rows = handoff.get("wall_basis") or []
    if wall_rows:
        lines += ["", "## 墙钟基准（冻结件声明 vs 一次性处置）", "",
                  "| 产物目录 | 冻结文件 | 基准（秒/桌） | 来源 |",
                  "| --- | --- | ---: | --- |"]
        for row in wall_rows:
            lines.append("| {0} | {1} | {2} | {3} |".format(
                row.get("out"), row.get("freeze_path"),
                _tables_text(row.get("seconds_per_table"), missing="（缺失）"),
                {"declared": "冻结件实测声明", "legacy-declared": "**一次性的历史口径声明**",
                 "missing": "**缺失且未声明**"}.get(str(row.get("source")), str(row.get("source")))))
    env = handoff.get("throughput_environment")
    if env:
        lines += ["", "## 机时口径环境（R8：**两个口径分开读**）", "",
                  "- 状态：**{0}**".format(env.get("status")),
                  "- 来源：{0}".format("；".join(env.get("sources") or []) or "（无）")]
        lines.append("- 计数：post={0} / pre={1} / **unknown={2}**".format(
            (env.get("counts") or {}).get("post"), (env.get("counts") or {}).get("pre"),
            (env.get("counts") or {}).get("unknown")))
        # **更正留痕要进人读面**（wv24 低项②）：权威面里有的值其实是更正件补上的；md 不写这一行，
        # 读者就会把"补记出来的 implementation"当成产物当时自己写下的实测值。补记/更正分开标。
        for item in env.get("corrections_applied") or []:
            applied_paths = item.get("applied_paths") or []
            if not (item.get("corrections_file") or item.get("error") or applied_paths
                    or item.get("skipped")):
                continue
            lines.append("- 更正留痕：{0}（{1}）：应用 {2} 条、跳过 {3} 条{4}{5}".format(
                Path(item.get("source") or "").name,
                Path(item["corrections_file"]).name if item.get("corrections_file") else "无更正件",
                item.get("applied"), len(item.get("skipped") or []),
                "；**出错：{0}**".format(item["error"]) if item.get("error") else "",
                "；**已整体回退：产物一个字段都没改**" if item.get("rolled_back") else ""))
            for applied in applied_paths:
                lines.append("  - `{0}`：**{1}**（{2} → {3}）{4}".format(
                    applied.get("path"), applied.get("kind"),
                    _correction_value_text(applied.get("before"), applied.get("kind")),
                    _correction_value_text(applied.get("after"), applied.get("kind")),
                    "——原产物**没有**这个字段，是更正件按实测补上的" if applied.get("kind") == "补记" else ""))
            for discarded in item.get("discarded_applied_paths") or []:
                lines.append("  - `{0}`：**已回退（未生效）**（{1} → {2}）".format(
                    discarded.get("path"),
                    _correction_value_text(discarded.get("before"), discarded.get("kind")),
                    _correction_value_text(discarded.get("after"), discarded.get("kind"))))
        tables = [("**启用内核后**（报价用这个口径）", "post_kernel_measurements"),
                  ("**启用内核前**（不得与新值混用）", "pre_kernel_measurements")]
        if (env.get("counts") or {}).get("unknown"):
            # **第三态也要有人读面**（wv22 L1）：否则 md 只显示"启用前（无）"，
            # 读者看不出还有"证据缺失"这一类。
            tables.append(("**证据缺失（unknown：不得当作启用前，也不得当作启用后）**",
                           "unknown_backend_measurements"))
        for label, key in tables:
            note = ""
            rows_env = env.get(key) or []
            lines += ["", "### {0}{1}".format(label, note), ""]
            if not rows_env:
                lines.append("（无）")
                continue
            # **来源账目要进表**（wv24 低项①）：同一个 --throughput-env 可以挂多个运行目录，
            # 不带账目列时读者分不清"这条臂是哪一次跑、算在哪本账上"。
            lines += ["| 臂 | 账目（运行目录） | 桌 | 墙钟秒/桌 | CPU 秒/桌 | 指令数/桌 | implementation | 测量时刻 |",
                      "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |"]
            for row in rows_env:
                lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
                    row.get("arm"),
                    "{0}（{1}）".format(
                        row.get("account") or ("（无记账记录：账户 {0}）".format(
                            "、".join(row.get("opened_accounts") or []))
                            if row.get("account_basis") == "opened" else "（无台账）"),
                        row.get("run_label") or "—"),
                    _tables_text(row.get("tables")),
                    _tables_text(row.get("wall_seconds_per_table"), missing="—"),
                    _tables_text(row.get("cpu_seconds_per_table"), missing="—"),
                    row.get("instructions_per_table") or "—",
                    row.get("implementation") or "—", row.get("measured_at_utc") or "—"))
        lines += ["", "- 报价规则：{0}".format(env.get("quote_rule"))]
        if env.get("instruction"):
            lines.append("- **{0}**".format(env["instruction"]))
    contract = handoff.get("consumption_contract")
    if contract:
        lines += ["", "### 消费契约（R2）", "",
                  "- **权威读数面**：{0}".format(contract["authoritative"]),
                  "- 档案的角色：{0}".format(contract["archive_role"]),
                  "- 为什么：{0}".format(contract["why"])]
    rescan = handoff.get("gate_rescan")
    if rescan:
        lines += ["", "## 准入重扫（报告侧；档案不动）", "",
                  "- 读的目录：{0}".format("；".join(rescan["dirs"])),
                  "- 修正的候选：{0}".format(
                      "；".join("{0}：{1} → {2}".format(item["candidate"], item["before"],
                                 item["after"]) for item in rescan["changed"]) or "（无）"),
                  "- 边界：`archive.json` 保留**它自己那次运行当时**的 gate 快照；",
                  "  报告里的 `gate` 带 `rescanned_by` 标明来源。两者不一致时以**记录文件**为准。"]
    binding = handoff.get("freeze_binding") or []
    if binding:
        lines += ["", "## 冻结绑定核对（台账原值 vs 当前文件）", "",
                  "| 产物目录 | 台账记录 sha256 | 文件当前 sha256 | 绑定 |",
                  "| --- | --- | --- | --- |"]
        for row in binding:
            lines.append("| {0} | `{1}` | `{2}` | {3} |".format(
                row["out"], (row["ledger_recorded_sha256"] or "-")[:16],
                (row["file_current_sha256"] or "-")[:16],
                "一致" if row["bound"] else "**不一致**"))
    lines += ["## 缺口", ""]
    for gap in handoff["gaps"]:
        lines.append("- **{0}**：{1}".format(gap.get("kind"), gap.get("impact")))
        # 定位字段先出：读者要能一眼看出"这一条说的是哪个候选/哪一级/哪本账"。
        for key, label in _GAP_LOCATOR_FIELDS:
            value = gap.get(key)
            if value is None or value == "" or value == [] or value == {}:
                continue
            lines.append("  - {0}：{1}".format(label, _render_gap_value(value)))
        if gap.get("items"):
            lines.append("  - 涉及：{0}".format("；".join(str(item) for item in gap["items"])))
        if gap.get("reasons"):
            lines.append("  - 原因（逐条取自候选档案）：{0}".format(
                "；".join(str(item) for item in gap["reasons"])))
        if gap.get("action"):
            lines.append("  - 处置建议：{0}".format(gap["action"]))
    lines += ["", "## 交第四阶段", "",
              "- 交接对象：{0}".format(handoff["next_stage"]["handoff_to"])]
    for item in handoff["next_stage"]["do_not_reuse"]:
        lines.append("- 不得复用：{0}".format(item))
    for item in handoff["next_stage"]["required_before_confirm"]:
        lines.append("- 确认前置：{0}".format(item))
    return "\n".join(lines) + "\n"


def render_plan_md(plan: Mapping[str, Any]) -> str:
    arithmetic = plan["arithmetic"]
    lines = ["# 坐隐 3.4 搜索计划（先冻结后执行）", "",
             "冻结文件：`{0}`（sha256 `{1}`）".format(
                 plan["freeze_path"], short(plan["freeze_sha256"], 16)), "",
             "## 规模核算", "", "| 项 | 值 |", "| --- | ---: |"]
    for key in ("per_candidate_tables", "upgrade_tables", "stage_tables",
                "retry_reserve_tables", "fixed_reserve_tables", "search_tables",
                "c_max_by_budget", "candidates_available", "candidates_planned",
                "t_l1_tables", "total_planned_tables", "unallocated_tables"):
        lines.append("| {0} | {1} |".format(key, arithmetic[key]))
    lines += ["", "## 冻结停止规则", ""]
    for key, value in sorted(plan["stop_rules"].items()):
        lines.append("- `{0}`：{1}".format(key, value))
    lines += ["", "## 预算（四维 × 两账）", "",
              "| 账户 | 调用 | 输出 token | 桌数 | 墙钟秒 |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for account in ("search", "confirm"):
        limits = plan["search_account"] if account == "search" else plan["confirm_account"]
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            account, limits["calls"], limits["output_tokens"], limits["tables"],
            limits["wall_clock_sec"]))
    lines += ["", "> {0}".format(plan["note"])]
    return "\n".join(lines) + "\n"


# ============================================================ 10. 内部解析辅助

def _last_json_object(text: str) -> Optional[Dict[str, Any]]:
    """从工具输出里取最后一个 JSON 对象（工具会在结束时打印一行 JSON 摘要）。"""

    if not text:
        return None
    depth, start = 0, None
    candidates: List[str] = []
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:index + 1])
    for chunk in reversed(candidates):
        try:
            data = json.loads(chunk)
        except Exception:                           # noqa: BLE001 —— 不是 JSON 就跳过
            continue
        if isinstance(data, dict):
            return data
    return None


def _budget_tokens(gen_out: Path) -> Optional[float]:
    """读生成端**自己**的累计 token 台账；读不到返回 None（**不是 0**）。

    返回 0 与返回 None 是两件不同的事：前者是"确实没消耗"，后者是"不知道"。
    把"不知道"写成 0，等于给未知消耗开一条免费通道。
    """

    path = Path(gen_out) / "budget.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:                               # noqa: BLE001 —— 读不动就是不知道
        return None
    value = data.get("spent_tokens")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _usage_output_tokens(usage: Optional[Mapping[str, Any]]) -> Optional[float]:
    """从 usage 映射里取**输出** token。

    键集合与生成端的口径保持一致（它是用量产物的作者）；这里只取输出侧，
    因为预算维度是"输出 token"，输入侧不占这条预算。取不到返回 None，不猜 0。
    """

    if not isinstance(usage, Mapping):
        return None
    for key in ("output_tokens", "outputTokens", "completion_tokens"):
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def read_token_usage(*, gen_out: Path, attempt_dir: Optional[str], before: Optional[float],
                     after: Optional[float]) -> Dict[str, Any]:
    """按**生成端产物**读出本次调用的输出 token 用量。

    优先级（都不重算用量本身，只做读取与累加）：
      ① 生成端台账 budget.json 的 spent_tokens 增量——生成端自己的口径；
      ② 尝试记录 record.json 里的 usage（delegate/replay 摄入路径不经过生成端台账）；
      ③ 两者都没有 ⇒ **known=False**，调用方按预留额保守计费并单独计数。

    headless 通道此前会把用量写成 tokens_unknown=true；生成端改为从会话日志累加后，
    这里会自动走 ①/②。记录里显式的 tokens_unknown 标记一律被尊重，不会被猜成 0。
    """

    if before is not None and after is not None and after > before:
        return {"known": True, "output_tokens": after - before,
                "source": "generate/budget.json 增量（生成端口径）"}
    record: Mapping[str, Any] = {}
    if attempt_dir:
        record_path = Path(attempt_dir) / "record.json"
        if record_path.is_file():
            try:
                loaded = json.loads(record_path.read_text(encoding="utf-8"))
                record = loaded if isinstance(loaded, Mapping) else {}
            except Exception:                       # noqa: BLE001 —— 读不动就是不知道
                record = {}
    usage = None
    reply = record.get("reply")
    if isinstance(reply, Mapping):
        usage = reply.get("usage")
    if usage is None and isinstance(record.get("usage"), Mapping):
        usage = record.get("usage")
    tokens = _usage_output_tokens(usage)
    if tokens is not None:
        return {"known": True, "output_tokens": tokens,
                "source": "generate 尝试记录 record.json 的 usage"}
    marked = bool((isinstance(reply, Mapping) and reply.get("tokens_unknown"))
                  or record.get("tokens_unknown")
                  or (isinstance(usage, Mapping) and usage.get("tokens_unknown")))
    reason = ("生成端记录显式标记 tokens_unknown（通道没有可用用量）" if marked
              else "生成端台账无 token 增量且尝试记录里没有 usage 字段")
    return {"known": False, "output_tokens": None, "source": None, "reason": reason}


def _code_sha_of(attempt_dir: Optional[str], base: Optional[Path] = None) -> Optional[str]:
    """生成产物的**源码指纹**。

    attempt_dir 是生成端给的**相对**路径，基准是它自己的 --out（即
    <run>/generate/<request_id>/），**不是本进程的工作目录**。早期版本少传了这层基准，
    于是相对路径在工作目录下找不到文件，source.code_sha256 被**静默记成 null**
    （本轮实测：replay 演练产物的指纹为空；交接时按 code_sha256_backfill 就地重算，见
    _enrich_generated_records）。空指纹既证明不了"产物没被换过"，也证明不了"没越界"。

    base=None 保留旧语义（按传入路径原样解析）；需要正确解析的调用方必须传 base。
    """

    if not attempt_dir:
        return None
    path = Path(attempt_dir)
    if not path.is_absolute() and base is not None:
        path = Path(base) / path
    code = path / "candidate.py"
    return sha256_file(code) if code.is_file() else None


def generation_evidence_strength(generation_out: Path,
                                 attempt_identity: str) -> Dict[str, Any]:
    """读生成端的尝试台账（records.jsonl），回答"这条产物是不是模型输出"。

    **为什么必须机器判定**：生成管线会让**演练夹具**（replay / origin=format_fixture）也走完
    解析与隔离装载，于是它和真实模型回复在档案里长得一样。若一并写进"待静态注册"缺口，
    处置建议（加模块 + 注册表一行）就会被照着执行——那是把**手工夹具**注册成候选，
    后续所有桌赛结果都会挂在一个没有生成来源的身份上。判据只能取自生成端自己写下的字段
    （is_model_output / evidence_kind / admission_eligible），本模块不推断。

    三态：model（真模型产出）/ drill（管线演练）/ unknown（读不到）。
    **unknown 是 fail-closed**：仍按"待注册"报，不因为查不到就降级放行。
    """

    unknown = {"strength": "unknown", "evidence_kind": None, "is_model_output": None,
               "admission_eligible": None, "source": None,
               "reason": "生成端尝试台账不可读或没有该尝试"}
    path = Path(generation_out) / "records.jsonl"
    if not path.is_file():
        return unknown
    found: Optional[Mapping[str, Any]] = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:                       # noqa: BLE001 —— 坏行不参与判定
                continue
            if isinstance(row, Mapping) and row.get("attempt_identity") == attempt_identity:
                found = row
                break
    except Exception:                               # noqa: BLE001 —— 读不动就是不知道
        return unknown
    if found is None:
        return unknown
    flag = found.get("is_model_output")
    if flag is True:
        strength = "model"
    elif flag is False:
        strength = "drill"
    else:
        strength = "unknown"
    return {"strength": strength,
            "evidence_kind": found.get("evidence_kind"),
            "is_model_output": flag if isinstance(flag, bool) else None,
            "admission_eligible": found.get("admission_eligible"),
            "source": str(path), "reason": ""}


#: 执行件（compare）报告的固定文件名与 schema（见 STAGE-COMPARE-CONTRACT.md §3）。
STAGE_COMPARE_REPORT = "stage-compare.json"
STAGE_COMPARE_SCHEMA = "sitin-stage-compare/1"


#: 执行件报告的**溯源字段**（契约 §3.5，F1）：缺任一即判"非合规报告"。
#:
#: 为什么必须有消费端：这些字段是"这份报告可不可信"的唯一机器线索。尤其
#: `tool_source_changed_during_run` 为真时，报告描述的那份源码**已经不是跑的时候那份**——
#: 只靠人读 prose 兜着，一个标志为真的报告会被**静默结算**（组合评审 F1 的要点）。
STAGE_PROVENANCE_FIELDS: Tuple[str, ...] = (
    "versions.tool_sha256", "source_digest_at_start", "source_digest_at_end",
    "tool_source_changed_during_run", "budget.precheck",
)


def _dotted(report: Mapping[str, Any], dotted: str) -> Any:
    """按点号路径取值（`budget.precheck` 这类字段落在嵌套里）；缺失返回 None。"""

    node: Any = report
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def stage_provenance(report: Mapping[str, Any]) -> Dict[str, Any]:
    """读执行件报告的溯源字段，并给出**机器可判**的合规结论。

    三种结局，机器字段里各有一席：
      - `compliant=True`：五字段齐备；
      - `compliant=False`：缺字段（很可能是字段落地之前的产物）⇒ 记 `missing_fields`，
        让"非合规报告"与合规报告在**机器层面**可区分，而不是只靠 README 的散文；
      - `source_changed_during_run=True`：运行中源码被改 ⇒ 该报告**不可作结论依据**，
        调用方必须记 problem 并把该臂标为不受信（桌数仍按实报结算——桌是真的跑过了）。
    """

    missing = [name for name in STAGE_PROVENANCE_FIELDS if _dotted(report, name) is None]
    changed = _dotted(report, "tool_source_changed_during_run")
    return {
        "compliant": not missing,
        "missing_fields": missing,
        "source_changed_during_run": changed if isinstance(changed, bool) else None,
        "tool_sha256": _dotted(report, "versions.tool_sha256"),
        "source_digest_at_start": _dotted(report, "source_digest_at_start"),
        "source_digest_at_end": _dotted(report, "source_digest_at_end"),
        "precheck": _dotted(report, "budget.precheck"),
        "required_tables": _dotted(report, "budget.required_tables"),
        "note": ("执行件溯源字段齐备" if not missing else
                 "**非合规报告**：缺 {0}（该报告可能是这些字段落地之前的产物）".format(missing)),
    }


def _read_stage_compare_report(arm_dir: Path) -> Tuple[Optional[Mapping[str, Any]], str]:
    """读执行件的对账报告；缺文件/schema 不符一律**显式**返回问题，不猜。"""

    path = Path(arm_dir) / STAGE_COMPARE_REPORT
    if not path.is_file():
        return None, "缺少 {0}（按接口约定必须落盘）".format(STAGE_COMPARE_REPORT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                        # noqa: BLE001 —— 读不动就是对不上账
        return None, "报告无法解析：{0}".format(exc)
    if not isinstance(data, Mapping):
        return None, "报告不是 JSON 对象"
    if data.get("schema") != STAGE_COMPARE_SCHEMA:
        return None, "报告 schema 应为 {0}，得到 {1!r}".format(
            STAGE_COMPARE_SCHEMA, data.get("schema"))
    return data, ""


def _stage_tables_spent(report: Mapping[str, Any]) -> Optional[float]:
    """取对账唯一字段 tables.spent；取不到返回 None（调用方按预留额保守计费）。"""

    tables = report.get("tables")
    if not isinstance(tables, Mapping):
        return None
    value = tables.get("spent")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _scheduler_spent_tables(ledger_path: Path) -> float:
    """读调度器台账里**已经累计**的桌数；没有台账就是 0（不是"未知"）。

    只用于取增量：本步的实扣 = 调用后累计 − 调用前累计。
    """

    if not Path(ledger_path).is_file():
        return 0.0
    try:
        data = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    except Exception:                               # noqa: BLE001 —— 读不动按 0，增量会偏保守
        return 0.0
    value = data.get("spent_tables")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _read_level_results(elimination_path: Path, level: str) -> Dict[str, Dict[str, Any]]:
    """从调度器产物里读回某一级的逐候选根级统计（键是绑定身份）。"""

    if not Path(elimination_path).is_file():
        return {}
    try:
        data = json.loads(Path(elimination_path).read_text(encoding="utf-8"))
    except Exception:                               # noqa: BLE001 —— 读不动按“没有结果”
        return {}
    for item in (data.get("report") or {}).get("levels", ()):
        if item.get("round") == level:
            return dict(item.get("results") or {})
    return {}


def _stage_tables_cap(freeze: Freeze) -> Optional[int]:
    """执行件的桌数**硬上限**（每个臂）：场景数 × 会话上界 × 臂数。

    会话上界（含加赛）由执行件的阶段合同决定，冻结文件里用 `tables_per_run_upper` 声明
    （缺省退化为期望值 `tables_per_run`）。**编排者预留与这里是同一个值**。
    """

    stage = freeze.stage
    upper = stage.get("tables_per_run_upper", stage.get("tables_per_run"))
    try:
        return int(stage["pairs"]) * int(upper) * int(stage["arms"])
    except (KeyError, TypeError, ValueError):
        return None


def select_upgrade_queue(ranked_survivors: Sequence[Mapping[str, Any]],
                         exploration_entries: Sequence[Mapping[str, Any]],
                         slots: int) -> List[Dict[str, Any]]:
    """升级名额分配（**运行前冻结的规则**）。

    规则（PLAN §2「L1 保留部分评分靠前者，并预留机制不同或尚未分辨者的探索名额」）：
      - 容量 >= 2 时，**探索名额先占一个**——否则"探索名额"只是标签，换不来样本；
      - 其余名额按**评分序**（留存规则给出的名次）填，不按候选名字典序。

    抽成纯函数是为了可测：名额分配是最容易写错、也最难从产物看出来的一步。
    """

    queue: List[Dict[str, Any]] = []
    if int(slots) >= 2 and exploration_entries:
        queue.extend(dict(entry) for entry in exploration_entries[:1])
    for entry in ranked_survivors:
        if len(queue) >= int(slots):
            break
        queue.append(dict(entry))
    return queue[:max(0, int(slots))]


def level_has_samples(ctx: SearchContext, entry: Mapping[str, Any], level: str) -> bool:
    """该候选在这一级**是否真的拿到了样本**（按档案里的统计判断，不看计划）。"""

    record = ctx.archive.records.get(str(entry["key"]))
    if record is None:
        return False
    return bool((record.levels.get(level) or {}).get("statistics"))


def _screen_timeout(panel: Mapping[str, Any], candidates: int) -> float:
    """评估步的墙钟上限：按调度器自己的单轮公式 × 候选数，再留一倍余量。"""

    sched = _sibling("sitin_scheduler")
    per_candidate = sched.round_timeout_sec(int(panel["roots"]) * int(panel["seats"]) * 2)
    return per_candidate * max(1, int(candidates)) * 2.0 + 120.0


def _hypotheses(pool: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    merged: Dict[str, str] = dict(pool.get("hypotheses") or {})
    for entry in entries:
        if entry.get("hypothesis"):
            merged[entry["key"]] = str(entry["hypothesis"])
    return merged


# ============================================================ 11. 命令实现

def _resolve_pool_entries(pool: Mapping[str, Any],
                          admission: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """把候选池 + 准入核验结果合成“值得花桌数”的条目。"""

    by_name = {item["candidate"]: item for item in admission}
    entries: List[Dict[str, Any]] = []
    for raw in pool.get("candidates", ()):
        name = raw.get("candidate")
        item = by_name.get(name)
        entries.append({
            "key": name,
            "candidate": name,
            "weights": dict(raw.get("weights") or {}),
            "identity": (item or {}).get("identity") or name,
            "admission": dict(item or {}),
            "hypothesis": raw.get("stage_hypothesis") or "",
        })
    return entries


def _admitted_only(entries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(entry) for entry in entries
            if (entry.get("admission") or {}).get("status") == "admitted"]


def cmd_plan(args: Any) -> int:
    freeze = Freeze.load(Path(args.freeze))
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    pool = load_pool(Path(args.pool) if args.pool else None, args.candidate, args.weights)
    plan = compute_plan(freeze, available=args.available if args.available is not None
                        else len(pool["candidates"]))
    plan["pool"] = {"candidates": [entry.get("candidate") for entry in pool["candidates"]],
                    "generated": [item.get("attempt_dir") for item in pool["generated"]]}
    write_json(out / "plan.json", plan)
    (out / "plan.md").write_text(render_plan_md(plan), encoding="utf-8")
    print(json.dumps({"ok": True, "candidates_planned": plan["arithmetic"]["candidates_planned"],
                      "total_planned_tables": plan["arithmetic"]["total_planned_tables"],
                      "unallocated_tables": plan["arithmetic"]["unallocated_tables"]},
                     ensure_ascii=False))
    return 0


def measured_wall_throughput(ledger: "SearchLedger") -> Tuple[Optional[float], float, float]:
    """从**已结算**的评估步里算实测秒/桌（返回 (秒/桌, 桌数, 墙钟秒)）。

    为什么从账本算：写死的"7.9 秒/桌"会随时间失真（评审 F3），而账本本来就逐笔记着"这一步花了几桌、
    实测几秒"——报价该由**当前这批数据**渲染，而不是抄一句历史文案。
    """

    tables = 0.0
    wall = 0.0
    for item in ledger.reservations:
        if item.get("status") != "settled" or item.get("account") != ACCOUNT_SEARCH:
            continue
        step_tables = float(item["charged"].get("tables") or 0.0)
        step_wall = float(item["charged"].get("wall_clock_sec") or 0.0)
        if step_tables > 0 and step_wall > 0:
            tables += step_tables
            wall += step_wall
    return ((wall / tables) if tables else None, tables, wall)


def _record_wall_basis_declaration(ctx: SearchContext, basis: Mapping[str, Any]) -> Dict[str, Any]:
    """记一条"本账的墙钟基准来自遗留口径"的显式声明（只追加；同一冻结件只记一次）。

    这不是兼容层：历史常数已作废，**缺声明就该报错**；只有产生于规则生效之前的旧冻结件才允许被
    **点名**使用，而且这一步必须能在产物里看到（否则后人不清楚某个超限是"实测报错"还是"历史口径"）。
    """

    path = ctx.out / WALL_BASIS_FILE
    existing = [row for row in _read_jsonl(path) if row.get("freeze_sha256") == basis.get("freeze_sha256")]
    if existing:
        return existing[0]
    record = {"schema": "sitin-wall-basis-declaration/1", "at_utc": utc_now(),
              "freeze_path": basis.get("freeze_path"), "freeze_sha256": basis.get("freeze_sha256"),
              "seconds_per_table": basis.get("seconds_per_table"), "source": "legacy-declared",
              "value_note": basis.get("value_note"), "reason": basis.get("reason"),
              "boundary": "该冻结件产生于 fail-closed 规则生效之前；此值**非实测**，不得用于新报价"}
    ctx.log({"step_id": "wall-basis", "status": "legacy-declared",
             "freeze_path": record["freeze_path"], "reason": record["reason"]})
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """读一行一条的 JSONL；缺文件或坏行都不参与判定。"""

    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:                       # noqa: BLE001
            continue
        if isinstance(data, Mapping):
            rows.append(dict(data))
    return rows


def _record_overrun_acknowledgement(ctx: SearchContext,
                                    detail: Mapping[str, Any]) -> Dict[str, Any]:
    """记一条"操作者已读过该超限报告并决定继续"的知情记录（只追加，不改任何数）。

    **为什么必须有留痕而不是静默放行**：一本账里一旦有步超出预留，"超限即停"就已经生效并
    如实记账（停止原因、实结值都在）。之后是否继续，是**操作者读过报告之后的决定**，
    与"没人看见就过去了"是两件事。这条记录的唯一目的就是把二者区分开。

    **它不改任何东西**：charged 保持实结值、overrun 标记保持为真、不重结、不新增预留。
    """

    axis = next(iter(detail.get("axes") or {}), "")
    record = {
        "schema": OVERRUN_ACK_SCHEMA,
        "at_utc": utc_now(),
        "step_id": detail["step_id"],
        "reservation_id": detail.get("reservation_id"),
        "account": detail.get("account"),
        "axes": dict(detail.get("axes") or {}),
        "axis": axis,
        "unchanged": {"charged": True, "overrun_flag": True, "resettlement": False},
        "reason": "操作者逐条点名确认已读过本步的超限报告：该停止已在上一次运行中生效并如实记账，本次运行只是继续执行**后续步骤**；不改 charged 值、不清 overrun 标记、不重结。墙钟维度的超限常见于**预留口径失真**（例如仍用历史吞吐常数），不等于实际多花了预算。",
    }
    # 点名之后，那条停止原因**不再是当前状态**：留着会让 status 继续报"已停止"，
    # 与"已继续执行并跑完"直接矛盾。清掉当前状态并留痕（历史仍在 steps.jsonl 与本文件里）。
    if detail["step_id"] in str(ctx.state.stop_reason or ""):
        previous = str(ctx.state.stop_reason)
        ctx.state.stop_reason = None
        ctx.state.notes.append("{0} 点名越过超限后清除停止原因：{1}".format(utc_now(), previous))
    ctx.log({"step_id": detail["step_id"], "status": "overrun-acknowledged",
             "reservation_id": detail.get("reservation_id"), "axes": record["axes"],
             "reason": record["reason"]})
    # 同一步同一数值只留一条：重复运行（步被判"复用"）不该把同一件事记两遍。
    existing = [row for row in _load_overrun_acknowledgements(ctx.out)
                if row.get("step_id") == detail["step_id"]
                and row.get("axes") == record["axes"]]
    if existing:
        return existing[0]
    path = ctx.out / OVERRUN_ACK_FILE
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _overrun_gate(ctx: SearchContext, step_id: str,
                  acknowledged: Sequence[str]) -> Optional[str]:
    """「超限即停」判据：默认照停；被**逐条点名**的步改为留痕放行。

    边界：点名必须逐条给出 step_id（没有通配、没有默认开启）；点名只影响"是否继续执行后续步骤"，
    不改变本步已结算的任何数字。未点名的步一律照旧停止——这条是回归必须钉住的行为。
    """

    detail = ctx.overrun_detail(step_id)
    if detail is None:
        return None
    if step_id not in tuple(acknowledged or ()):
        return detail["summary"]
    _record_overrun_acknowledgement(ctx, detail)
    return None


def _load_overrun_acknowledgements(out: Path) -> List[Dict[str, Any]]:
    """读某本账的知情记录（一行一条）；文件不存在就是没有，不是错误。"""

    path = Path(out) / OVERRUN_ACK_FILE
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:                           # noqa: BLE001 —— 坏行不参与判定
            continue
        if isinstance(row, Mapping):
            rows.append(dict(row, out=str(out)))
    return rows


def _overrun_acknowledgement_gap(row: Mapping[str, Any]) -> Dict[str, Any]:
    """把一条知情记录变成交接件的**已披露例外**条目。"""

    axes = row.get("axes") or {}
    axis = str(row.get("axis") or next(iter(axes), ""))
    detail = axes.get(axis) or {}
    impact = ("**已披露例外**：本步**超出预留**（维度 {0}：预留 {1} / 实结 {2}），停止规则已在当时生效并如实记账；随后由操作者**逐条点名**确认后继续执行后续步骤。本条存在的意义是让后人看到「为什么一本已有超限记录的账还在继续跑」。边界：**没有**改 charged 值、**没有**清 overrun 标记、**没有**重结。").format(axis, detail.get("预留"), detail.get("实结"))
    action = ("若要复核这条决定，读 steps.jsonl 与 " + OVERRUN_ACK_FILE + " 的同一 step_id；若超限来自**预留口径失真**（如墙钟仍用历史吞吐常数），应按实测吞吐重报后重新冻结，而不是把它当成「实际多花了预算」。")
    return {
        "kind": "overrun_acknowledged_exception",
        "step_id": row.get("step_id"),
        "axis": axis,
        "reserved": detail.get("预留"),
        "charged": detail.get("实结"),
        "at_utc": row.get("at_utc"),
        "out": row.get("out"),
        "impact": impact,
        "action": action,
    }

def cmd_run(args: Any) -> int:
    freeze = Freeze.load(Path(args.freeze))
    # **纯读预检**（评审 F13）：缺声明且未显式处置时**在这里就报错**——
    # 不写任何产物、不发生任何生成调用。"验证失败"绝不能发生在已经花了钱之后。
    freeze.wall_basis(getattr(args, "legacy_wall_basis", None))
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    ledger = SearchLedger.load(out / "ledger.json", freeze)
    archive = Archive.load(out / "archive.json", freeze)
    state = RunState.load(out / "state.json")
    # 记下本目录用的是哪份冻结：多轮汇总（freeze --also）靠它找到各自的冻结与摘要。
    (out / "freeze-path.txt").write_text(str(freeze.path) + "\n", encoding="utf-8")
    ctx = SearchContext(out=out, freeze=freeze, ledger=ledger, archive=archive, state=state,
                        steps_path=out / "steps.jsonl", dry_run=bool(args.dry_run),
                        allow_rerun=bool(args.allow_rerun),
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    pool = load_pool(Path(args.pool) if args.pool else None, args.candidate, args.weights)

    # ① 生成（可选）：只产出离线产物与注册请求，**不注册任何东西**。
    generation: List[Dict[str, Any]] = []
    if args.generation_plan:
        plan_data = json.loads(Path(args.generation_plan).read_text(encoding="utf-8"))
        if plan_data.get("schema") != GENERATION_PLAN_SCHEMA:
            raise ValueError("生成计划 schema 必须是 {0}".format(GENERATION_PLAN_SCHEMA))
        limit = int(freeze.stop_rules["consecutive_failures"])
        for request in plan_data.get("requests", ()):
            outcome = step_generate(ctx, request, timeout_sec=float(args.gen_timeout_sec),
                                    token_reserve=int(args.gen_token_reserve))
            generation.append(outcome)
            failures = [item for item in generation if item.get("status") == "failed"]
            if len(failures) >= limit:
                state.stop_reason = "连续生成失败达到冻结上限 {0}".format(limit)
                state.save()
                break
            # 用量未知的调用达到上限即停：未知消耗既保守计费又单独封顶，
            # 否则"读不到用量"就会变成绕过 token 预算的通道。
            unknown = ctx.ledger.unknown_token_calls(ACCOUNT_SEARCH)
            if unknown >= int(freeze.stop_rules["unknown_token_call_limit"]):
                state.stop_reason = (
                    "输出 token 用量未知的调用达到冻结上限 {0} 次："
                    "消耗不可核对，保守停止".format(unknown))
                state.save()
                break

    # ② 准入核验（轻量）
    # --gate-records 可重复：门禁记录由各包落在自己的可写目录，消费侧必须能同时读多处
    # （不复制记录 ⇒ 不会出现两份会分叉的副本）。
    gate_dirs = as_gate_dirs(args.gate_records)
    entries = _resolve_pool_entries(pool, step_admission(
        ctx, pool.get("candidates", ()),
        gate_dirs=gate_dirs,
        admission_corpus=Path(args.admission_corpus) if args.admission_corpus else None))
    for entry in entries:
        status = entry["admission"].get("status")
        record = ctx.archive.upsert(
            entry["key"], candidate=entry["candidate"], weights=entry["weights"],
            identity=entry["identity"],
            registration=entry["admission"].get("registration") or "unknown",
            gate=dict(entry["admission"]),
            source={"kind": "registered_candidate"})
        if record.verdict == "pending":
            record.verdict = "pending" if status == "admitted" else "blocked"
            record.verdict_reason = ("" if status == "admitted"
                                     else "准入未通过：{0}".format(status))
    ctx.save()
    ctx.log({"step_id": "admission", "status": "ok",
             "admitted": [entry["key"] for entry in _admitted_only(entries)],
             "blocked": [{"key": entry["key"], "status": entry["admission"].get("status"),
                          "identity": entry["admission"].get("identity"),
                          "reason": entry["admission"].get("reason")} for entry in entries
                         if entry["admission"].get("status") != "admitted"]})

    admitted = _admitted_only(entries)
    plan = compute_plan(freeze, available=len(admitted))
    planned = int(plan["arithmetic"]["candidates_planned"])
    queue = sorted(admitted, key=lambda item: item["key"])[:planned] if planned else []
    if not queue:
        state.stop_reason = "没有可执行候选（准入通过 {0}，预算允许 {1}）".format(
            len(admitted), planned)
        state.save()
        ctx.save()
        print("停止：{0}".format(state.stop_reason))
        return 0

    # ③ 初筛（冻结面板）
    panel_data = freeze.panel
    # 两个等级名都可声明：台账**按步 id 唯一**（防重复计费），所以"同一本账里再加一个候选"
    # 必须能命名它的两级，否则第二级会撞上已完成的 screen:L2 而被判"复用"、拿不到样本。
    # 面板身份与等级名**无关**（只由 seed + 换座 + 基线 + 规则版本决定，见 panel_identity），
    # 因此换名不改变可比性：同名面板仍是同一批牌山。
    level = str(args.level_name or "L1")
    up_level = str(args.upgrade_level_name or "L2")
    # 逐条点名的"越过已报告超限"（默认空 = 一切照停；没有通配、没有开关式放行）。
    acknowledged = tuple(args.acknowledge_overrun or ())
    panel = plan_level(level=level, roots=int(panel_data["roots"]),
                       seats=int(panel_data["seats"]), seed_base=int(panel_data["seed_base"]),
                       root_prefix=str(panel_data["root_prefix"]))
    panel["panel_id"] = panel_identity(panel, baseline_id=str(panel_data["baseline_id"]),
                                       ruleset=str(panel_data["ruleset"]))
    panel["root_set_id"] = _sibling("sitin_scheduler").root_set_id_of(panel["root_specs"])
    problems = check_panel_alignment([dict(entry, panel_id=panel["panel_id"]) for entry in queue],
                                     level=level)
    if problems:
        state.stop_reason = "；".join(problems)
        state.save()
        ctx.save()
        print("停止：{0}".format(state.stop_reason))
        return 1
    # 调度器只接受**一个** --gate-records 目录：队列里的候选必须落在同一个目录里，
    # 否则 fail-closed 停下（静默挑一个会让部分候选被拒、白跑一遍）。
    queue_gate_dir = _screen_gate_dir(queue, fallback=gate_dirs[0] if gate_dirs else None)
    if queue_gate_dir is None:
        state.stop_reason = ("队列里的候选其门禁记录不在同一个目录（调度器只接受一个 "
                             "--gate-records）：{0}；**不挑目录**，fail-closed 停止".format(
                                 sorted({str(path) for entry in queue
                                         for path in ((entry.get("admission") or {}).get(
                                             "record_paths") or [])})))
        state.save()
        ctx.save()
        print("停止：{0}".format(state.stop_reason))
        return 1
    spec = {"name": level, "roots": panel["roots"], "seats": panel["seats"],
            "keep_fraction": float(freeze.stop_rules["keep_fraction"])}
    screen = step_screen(ctx, level=level, entries=queue, panel=panel, spec=spec,
                         gate_dir=queue_gate_dir,
                         admission_corpus=Path(args.admission_corpus),
                         timeout_sec=float(args.screen_timeout_sec)
                         if args.screen_timeout_sec else _screen_timeout(panel, len(queue)))
    if screen.get("status") == "failed":
        state.stop_reason = "初筛未产出可用结果：{0}".format(
            "；".join(screen.get("problems") or []) or "工具失败")
        state.save()
        ctx.save()
        print("停止：{0}".format(state.stop_reason))
        return 1
    # **只在"本步真的跑了"时才判超限**（F12 同类）：reused 的步这一轮没花任何东西，
    # 它历史上那条超限已经生效并如实记账；拿它挡住一次纯复跑，等于让"已完成的步复用"不成立。
    overrun = (None if screen.get("status") == "reused"
               else _overrun_gate(ctx, "screen:{0}".format(level), acknowledged))
    if overrun:
        # **超限即停**：超出预留（含墙钟）就不再往后推进，如实记停止原因。
        state.stop_reason = "初筛超出预留（超限即停）：{0}".format(overrun)
        state.save()
        ctx.save()
        print("停止：{0}".format(state.stop_reason))
        return 1
    promote = step_promote(ctx, level=level, entries=queue, hypotheses=_hypotheses(pool, queue))
    exploration_keys = [item["key"] for item in promote["exploration"]]
    by_key = {entry["key"]: entry for entry in queue}
    # 晋级集合按**评分序**（select_survivors 的名次）排列，而不是按候选名字典序：
    # 名额有限时"谁先拿样本"必须由留存规则决定。
    ranked_survivors = [by_key[key] for key in promote["promoted"] if key in by_key]
    exploration_entries = [by_key[key] for key in exploration_keys if key in by_key]
    survivors = ranked_survivors + exploration_entries

    # ④ 升级（冻结名额；预算不足即停，不静默扩容）
    upgrade = freeze.upgrade
    if survivors and int(freeze.stop_rules["upgrade_slots"]) > 0:
        up_panel = plan_level(level=up_level, roots=int(upgrade["roots"]),
                              seats=int(upgrade["seats"]), seed_base=int(upgrade["seed_base"]),
                              root_prefix=str(upgrade["root_prefix"]))
        up_panel["panel_id"] = panel_identity(up_panel, baseline_id=str(panel_data["baseline_id"]),
                                              ruleset=str(panel_data["ruleset"]))
        up_panel["root_set_id"] = _sibling("sitin_scheduler").root_set_id_of(up_panel["root_specs"])
        slots = int(freeze.stop_rules["upgrade_slots"])
        upgrade_queue = select_upgrade_queue(ranked_survivors, exploration_entries, slots)
        up_spec = {"name": up_level, "roots": up_panel["roots"], "seats": up_panel["seats"],
                   "keep_fraction": 1.0}
        try:
            l2 = step_screen(ctx, level=up_level, entries=upgrade_queue, panel=up_panel, spec=up_spec,
                             gate_dir=queue_gate_dir,
                             admission_corpus=Path(args.admission_corpus),
                             timeout_sec=_screen_timeout(up_panel, len(upgrade_queue)))
            # **L2 失败与 L1 同等阻断**（Lead 逐项要求 A4）：升级级没有可用结果时，
            # 后面的阶段比较与交接就不该继续推进——否则会把"缺一层证据"的候选当完整的报出去。
            if isinstance(l2, Mapping) and l2.get("status") == "failed":
                state.stop_reason = "升级未产出可用结果：{0}".format(
                    "；".join(l2.get("problems") or []) or "工具失败")
                state.save()
                ctx.save()
            overrun = (None if (isinstance(l2, Mapping) and l2.get("status") == "reused")
                       else _overrun_gate(ctx, "screen:{0}".format(up_level), acknowledged))
            if overrun and not state.stop_reason:
                state.stop_reason = "升级超出预留（超限即停）：{0}".format(overrun)
                state.save()
                ctx.save()
        except BudgetExhausted as error:
            state.stop_reason = "升级预算不足：{0}".format(error)
            state.save()
            ctx.save()
        # 晋级但**没有升级级样本**的探索候选：在同一块升级面板上补跑一步（L2x），
        # 让"探索名额"真的换来样本、也让升级级结果**同面板可比**。
        # 判据用"档案里到底有没有样本"，而不是"计划里有没有名额"——恢复运行（步被复用）时，
        # 计划名额与实际样本会不一致，只有前者会把这件事悄悄盖过去。
        leftover = [entry for entry in exploration_entries
                    if not level_has_samples(ctx, entry, up_level)]
        if leftover and not state.stop_reason:
            # 补样级的名字跟着升级级走：默认仍是 L2x（历史步 id 不变），改名后不撞旧步。
            l2x_level = "{0}x".format(up_level)
            l2x_spec = dict(up_spec, name=l2x_level)
            try:
                l2x = step_screen(ctx, level=l2x_level, entries=leftover[:1], panel=up_panel,
                                  spec=l2x_spec, gate_dir=queue_gate_dir,
                                  admission_corpus=Path(args.admission_corpus),
                                  timeout_sec=_screen_timeout(up_panel, 1))
                # L2x 与 L1/L2 **同等阻断**：探索名额的样本同样进结论，缺了就如实停。
                if isinstance(l2x, Mapping) and l2x.get("status") == "failed":
                    state.stop_reason = "L2x（探索补样）未产出可用结果：{0}".format(
                        "；".join(l2x.get("problems") or []) or "工具失败")
                    state.save()
                    ctx.save()
                overrun = (None if (isinstance(l2x, Mapping) and l2x.get("status") == "reused")
                           else _overrun_gate(ctx, "screen:{0}".format(l2x_level), acknowledged))
                if overrun and not state.stop_reason:
                    state.stop_reason = "L2x 超出预留（超限即停）：{0}".format(overrun)
                    state.save()
                    ctx.save()
            except BudgetExhausted as error:
                state.stop_reason = "探索名额样本预算不足：{0}".format(error)
                state.save()
                ctx.save()

    # ⑤ 阶段比较（能力探针 → 支持才花钱）
    if survivors and not state.stop_reason and args.stage_contract:
        step_stage(ctx, entries=survivors,
                   stage_plan={"candidate_policy": survivors[0].get("candidate"),
                               "pairs": int(freeze.stage["pairs"]),
                               "tables_per_run": int(freeze.stage["tables_per_run"]),
                               "arms": int(freeze.stage["arms"]),
                               "participants": int(freeze.stage["participants"]),
                               "contract_file": str(args.stage_contract)})
    ctx.save()
    print(json.dumps({"ok": True, "stop_reason": state.stop_reason,
                      "admitted": [entry["key"] for entry in admitted],
                      "screened": [entry["key"] for entry in queue],
                      "promoted": promote["promoted"],
                      "exploration": [item["key"] for item in promote["exploration"]],
                      "search_remaining": ctx.ledger.remaining(ACCOUNT_SEARCH)},
                     ensure_ascii=False, indent=2))
    return 0


def seed_entries_from_archive(archive_path: Path, keys: Sequence[str]) -> List[Dict[str, Any]]:
    """从既有档案里播种候选条目（身份 / 参数 / 准入记录），供阶段比较单独一轮使用。

    为什么需要它：阶段比较是**独立的一步**（新冻结、新账本），但候选的身份与准入依据
    来自上一轮已经核验过的档案。重新从命令行拼一遍身份，等于把"门禁通过的那份配置"
    又抄一次——抄错一个字面量就会变成另一个身份（本轮已实测过 20 与 20.0 的差别）。
    """

    data = json.loads(Path(archive_path).read_text(encoding="utf-8"))
    records = data.get("records") or {}
    entries: List[Dict[str, Any]] = []
    for key in keys:
        record = records.get(key)
        if record is None:
            raise ValueError("档案里没有候选 {0!r}：{1}".format(key, archive_path))
        entries.append({
            "key": key,
            "candidate": record.get("candidate") or key,
            "weights": dict(record.get("weights") or {}),
            "identity": record.get("identity"),
            "admission": dict(record.get("gate") or {}),
            "gate_record": (record.get("gate") or {}).get("record_path"),
            "hypothesis": "",
        })
    return entries


def cmd_stage(args: Any) -> int:
    """只执行**阶段比较**一步（新冻结、新账本）：桌数按执行件报告的 tables.spent 透传。"""

    freeze = Freeze.load(Path(args.freeze))
    # **纯读预检**（F13）：先核墙钟基准，再写任何产物。
    freeze.wall_basis(getattr(args, "legacy_wall_basis", None))
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    ledger = SearchLedger.load(out / "ledger.json", freeze)
    archive = Archive.load(out / "archive.json", freeze)
    state = RunState.load(out / "state.json")
    (out / "freeze-path.txt").write_text(str(freeze.path) + "\n", encoding="utf-8")
    ctx = SearchContext(out=out, freeze=freeze, ledger=ledger, archive=archive, state=state,
                        steps_path=out / "steps.jsonl", dry_run=bool(args.dry_run),
                        allow_rerun=bool(args.allow_rerun),
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    keys = [item.strip() for item in (args.candidates or "").split(",") if item.strip()]
    if not keys:
        raise SystemExit("--candidates 必填：逗号分隔的档案键（候选名）")
    entries = seed_entries_from_archive(Path(args.from_archive), keys)
    # 阶段比较前**再核验一次准入**（身份 + 语料）：身份或语料变了就不该花桌数。
    admission = {item["candidate"]: item for item in step_admission(
        ctx, entries, gate_dir=Path(args.gate_records),
        admission_corpus=Path(args.admission_corpus))}
    for entry in entries:
        item = admission.get(entry["candidate"]) or {}
        record = ctx.archive.upsert(entry["key"], candidate=entry["candidate"],
                                    identity=item.get("identity") or entry["identity"],
                                    weights=entry["weights"], gate=dict(item),
                                    registration=item.get("registration") or "unknown",
                                    source={"kind": "seeded_from_archive",
                                            "archive": str(args.from_archive)})
        record.gate = dict(item)
    ctx.save()
    blocked = [entry["key"] for entry in entries
               if (admission.get(entry["candidate"]) or {}).get("status") != "admitted"]
    if blocked:
        ctx.log({"step_id": "stage:admission", "status": "blocked", "candidates": blocked})
        print(json.dumps({"ok": False, "blocked": blocked,
                          "reason": "阶段比较前准入核验未通过：不扣预算"}, ensure_ascii=False))
        return 1
    outcome = step_stage(ctx, entries=entries,
                         stage_plan={"candidate_policy": entries[0]["candidate"],
                                     "pairs": int(freeze.stage["pairs"]),
                                     "tables_per_run": int(freeze.stage["tables_per_run"]),
                                     "arms": int(freeze.stage["arms"]),
                                     "participants": int(freeze.stage["participants"]),
                                     "seed_base": int(freeze.stage.get("seed_base", 0)),
                                     "focal": freeze.stage.get("focal"),
                                     "wall_budget_sec": freeze.stage.get("wall_budget_sec"),
                                     "tables_cap_per_arm": _stage_tables_cap(freeze),
                                     "admission_corpus": str(Path(args.admission_corpus)),
                                     "contract_file": str(args.stage_contract)})
    # "reused"（步已完成、复用产物）也是成功结局：no-op 不该显示成失败。
    print(json.dumps({"ok": outcome.get("status") in ("ran", "reused", "dry_run"),
                      "status": outcome.get("status"),
                      "planned_tables": outcome.get("planned_tables"),
                      "actual_tables": outcome.get("actual_tables"),
                      "problems": outcome.get("problems"),
                      "search_remaining": ctx.ledger.remaining(ACCOUNT_SEARCH)},
                     ensure_ascii=False, indent=2))
    return 0 if outcome.get("status") in ("ran", "dry_run", "reused") else 1


def _arm_rows(results_path: Path) -> Dict[Tuple[str, str], Dict[str, List[Any]]]:
    """按 (场景, 换座) 归拢两臂的**行为可观测字段**（用于参数注入核验）。"""

    rows = [json.loads(line) for line in Path(results_path).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    grouped: Dict[Tuple[str, str], Dict[str, List[Any]]] = {}
    for row in rows:
        if row.get("status") != "complete":
            continue
        permutation = row.get("seat_permutation")
        if not isinstance(permutation, (list, tuple)):
            suffix = str(row.get("pair_id", "")).split(":")[-1]
            permutation = tuple(int(ch) for ch in suffix if ch.isdigit())
        key = (str(row.get("scenario_id")), "".join(str(item) for item in permutation))
        arm = str(row.get("result_id", "")).rsplit(":", 1)[-1]
        entry = grouped.setdefault(key, {})
        entry[arm] = {
            "scores_after": list(row.get("scores_after") or []),
            "official_ranks": row.get("official_ranks"),
            "completed_hands": row.get("completed_hands"),
            "expected_hands": row.get("expected_hands"),
        }
    return grouped


def cmd_verify_injection(args: Any) -> int:
    """"参数真的注入到候选里了吗"的**行为核验**（Lead 批准 4 桌）。

    背景：`seven_pairs_path_value` 的声明参数恰好等于模块默认值，于是"参数生效"与
    "参数被忽略"在行为上不可区分。本步用**非默认参数**（如 closer_bonus=8.0）对同一批
    牌山跑一条诊断对照臂：

      - 基线臂 = 该候选 + 声明参数；注入臂 = 该候选 + 非默认参数；
      - 同一场景同一换座下比较两臂的可观测输出（分数向量/名次/完成手数）；
      - 有任何一对不同 ⇒ **参数确实被注入且改变了行为**；
      - 全部相同 ⇒ **未观测到行为差异**——这**不证明**参数未注入（可能这些牌山没触发相关
        分支），更不是任何强度结论。

    **边界**：注入臂的参数**没有准入记录**（门禁只针对声明配置），因此本步只做"注入是否
    生效"的诊断，**不产出任何效果结论**；基线臂仍要求准入通过，以免拿一个不该跑的配置做诊断。
    """

    freeze = Freeze.load(Path(args.freeze))
    # **纯读预检**（评审 F13）：先核墙钟基准，再写任何产物、再发生任何花钱的调用。
    freeze.wall_basis(getattr(args, "legacy_wall_basis", None))
    verify = freeze.data.get("verify")
    if not isinstance(verify, Mapping):
        raise SystemExit("冻结文件缺少 verify 段：核验计划必须**先冻结后执行**")
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    ledger = SearchLedger.load(out / "ledger.json", freeze)
    archive = Archive.load(out / "archive.json", freeze)
    state = RunState.load(out / "state.json")
    (out / "freeze-path.txt").write_text(str(freeze.path) + "\n", encoding="utf-8")
    ctx = SearchContext(out=out, freeze=freeze, ledger=ledger, archive=archive, state=state,
                        steps_path=out / "steps.jsonl", dry_run=bool(args.dry_run),
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    candidate = str(verify["candidate"])
    weights_base = dict(verify.get("weights_base") or {})
    weights_injected = dict(verify.get("weights_injected") or {})
    roots = int(verify.get("roots", 1))
    seats = int(verify.get("seats", 1))
    seeds = [{"seed": int(verify.get("seed_base", 2026110000)) + index,
              "scenario_id": "verify-{0}".format(index)} for index in range(roots)]

    # 零成本支撑证据：两套参数必须构造出**不同身份**（必要条件的落盘痕迹）。
    gates = _sibling("sitin_gates")
    identity_base = (gates.supervised_prepare(candidate, weights_base) or {}).get("bound_identity")
    identity_injected = (gates.supervised_prepare(candidate, weights_injected) or {}).get("bound_identity")
    verify_dir = out / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    plan = {"schema": "sitin-param-injection-plan/1", "candidate": candidate,
            "weights_base": weights_base, "weights_injected": weights_injected,
            "roots": roots, "seats": seats, "seeds": seeds,
            "identity_base": identity_base, "identity_injected": identity_injected,
            "identities_differ": bool(identity_base and identity_injected
                                      and identity_base != identity_injected),
            "purpose": verify.get("purpose"),
            "boundary": "注入臂参数无准入记录：本步只诊断'注入是否生效'，不产出效果结论"}
    write_json(verify_dir / "plan.json", plan)

    step_id = "verify:param-injection"
    tables = roots * seats * 2
    wall_estimate = tables * ctx.wall_seconds_per_table(freeze) * WALL_SAFETY_FACTOR
    plan_step = ctx.step(step_id, account=ACCOUNT_SEARCH,
                         amounts={"tables": tables, "wall_clock_sec": wall_estimate},
                         note="参数注入核验：{0} 根 × {1} 换座 × 2 臂（候选 {2}）".format(
                             roots, seats, candidate))
    if plan_step["status"] == "reused":
        return 0
    reservation = plan_step["reservation"]

    challenger_id = "arm-inject"
    baseline_id = "arm-base"
    experiment = {
        "experiment_schema_version": 1, "kind": "matches", "clock_mode": "logical",
        "baseline_policy": {"policy_id": baseline_id, "name": candidate,
                            "weights": weights_base},
        "challenger_policy": {"policy_id": challenger_id, "name": candidate,
                              "weights": weights_injected},
        "opponent_pool": [{"policy_id": "opp-{0}".format(i), "name": "weighted_heuristic_v2",
                           "weights": {}} for i in range(3)],
        "tournament_config": {
            "schema_version": 1, "max_games": 1, "rounds_per_game": 8,
            "rules": {"ruleset_version": "hangma-mvp-v10-public-counts", "base_score": 1,
                      "you_cai_bi_kao": False},
            "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 1.0,
                       "discard_timeout_sec": 3.0}},
        "seeds": seeds,
        # 换座顺序与调度器**同源**（pair_id 的构造依赖它，两处不一致会让计划核验失败）
        "seat_permutations": [list(item) for item in
                              _sibling("sitin_scheduler").PLANNED_PERMUTATIONS[:seats]],
        "initial_dealer": 0, "initial_scores": [0, 0, 0, 0],
        "match_id_prefix": "sitin-verify", "primary_metric": "table_score_delta",
        "tie_method": "strict", "n_resamples": 200, "resample_seed": 2031,
    }
    write_json(verify_dir / "experiment.json", experiment)
    command = [tool_python(), _project_file(_PROJECT_ROOT, REPO_ROOT / "scripts/evaluate.py"), "matches",
               "--experiment", verify_dir / "experiment.json", "--out", verify_dir / "out"]
    run = run_tool("evaluate.matches", command, cwd=ctx.out,
                   timeout_sec=float(roots * seats * 60 + 300), dry_run=ctx.dry_run)
    if ctx.dry_run:
        ctx.ledger.release(reservation, reason="dry-run：只做计划，不执行注入核验")
        print(json.dumps({"ok": True, "dry_run": True, "tables": tables}, ensure_ascii=False))
        return 0
    results_path = verify_dir / "out/results.jsonl"
    verdict = (_sibling("sitin_scheduler").verify_round_plan(
        results_path, seeds, seats, baseline_id, challenger_id) if results_path.is_file()
        else {"ok": False, "problems": ["没有 results.jsonl"]})
    grouped = _arm_rows(results_path) if results_path.is_file() else {}
    compared, changed = [], []
    for key, arms in sorted(grouped.items()):
        base, injected = arms.get(baseline_id), arms.get(challenger_id)
        if not base or not injected:
            continue
        differs = {field: {"base": base[field], "injected": injected[field]}
                   for field in ("scores_after", "official_ranks", "completed_hands")
                   if base[field] != injected[field]}
        item = {"scenario": key[0], "permutation": key[1],
                "base_scores": base["scores_after"], "injected_scores": injected["scores_after"],
                "differs": differs}
        compared.append(item)
        if differs:
            changed.append(item)
    report = {
        "schema": "sitin-param-injection-report/1",
        "generated_at_utc": utc_now(),
        "plan": plan,
        "tool": run.to_json(),
        "plan_verification": verdict,
        "pairs_compared": len(compared), "pairs_changed": len(changed),
        "comparisons": compared,
        "conclusion": ("参数**确实被注入并改变了行为**：{0}/{1} 对在同一牌山上出现可观测差异".format(
            len(changed), len(compared)) if changed else
            "**未观测到行为差异**（0/{0} 对）：这不证明参数未注入（可能这些牌山没有触发相关"
            "分支），也不构成任何强度结论".format(len(compared))),
        "boundary": "诊断步：注入臂参数无准入记录，结果不得用作效果证据",
    }
    write_json(verify_dir / "report.json", report)
    actual_tables = float(len(compared) * 2) if compared else float(tables)
    ctx.ledger.settle(reservation,
                      status="ok" if verdict.get("ok") and run.ok else "failed",
                      actual={"tables": actual_tables, "wall_clock_sec": run.elapsed_sec},
                      note="注入核验：{0} 对可比、{1} 对出现差异".format(
                          len(compared), len(changed)))
    # 只写**真实候选键**：另起一个 "verify:<候选>" 键会在交接件里多出一条没有层级的空候选，
    # 看起来像"又有一个候选"（档案是给人看的清单，不是日志）。
    ctx.archive.upsert(candidate, identity=identity_base, registration="registered",
                       source={"kind": "param_injection_verify",
                               "report": str(verify_dir / "report.json")})
    ctx.archive.note(candidate, "参数注入核验：身份已区分（{0}）".format(
        "两套参数身份不同" if plan["identities_differ"] else "两套参数身份相同"))
    ctx.state.mark(step_id)
    ctx.save()
    ctx.log({"step_id": step_id, "status": "ok", "pairs_compared": len(compared),
             "pairs_changed": len(changed), "tables": actual_tables,
             "identities_differ": plan["identities_differ"],
             "tool": run.to_json()})
    overrun = ctx.overrun_of(step_id)
    if overrun:
        ctx.state.stop_reason = "参数注入核验超出预留（超限即停）：{0}".format(overrun)
        ctx.state.save()
    # **触发面接线验证**（0 桌）：裁定一的首选路径；冻结件里声明了 verify.wiring 段才跑。
    wiring_outcome: Optional[Dict[str, Any]] = None
    wiring = verify.get("wiring")
    if isinstance(wiring, Mapping):
        wiring_outcome = step_wiring_surface(ctx, candidate=candidate, verify=verify,
                                             wiring=wiring)
        if wiring_outcome.get("comparison"):
            comparison = wiring_outcome["comparison"]
            print(json.dumps({"wiring_branch_reached": comparison["branch_reached"],
                              "wiring_parameters_change_observable_behaviour":
                                  comparison["parameters_change_observable_behaviour"],
                              "wiring_verdict": comparison["verdict"]},
                             ensure_ascii=False, indent=2))
    print(json.dumps({"ok": bool(verdict.get("ok")) and run.ok,
                      "pairs_compared": len(compared), "pairs_changed": len(changed),
                      "identities_differ": plan["identities_differ"],
                      "tables": actual_tables, "conclusion": report["conclusion"],
                      "wiring": (wiring_outcome or {}).get("comparison"),
                      "report": str(verify_dir / "report.json")}, ensure_ascii=False, indent=2))
    return 0 if run.ok and not overrun else 1


def _g2_evidence(path: Path) -> Optional[Mapping[str, Any]]:
    """从门禁报告里取 G-2（退化检测）的 detail —— 触发面的接线证据就在这里。"""

    if not Path(path).is_file():
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                               # noqa: BLE001 —— 读不动就是没有证据
        return None
    for gate in data.get("gates", ()):
        if str(gate.get("gate", "")).startswith("G-2"):
            detail = gate.get("detail")
            return dict(detail, _gate_status=gate.get("status"),
                        _gate_problems=list(gate.get("problems") or ()),
                        _evidence_kind=data.get("evidence_kind"),
                        _admitted=data.get("admitted"))
    return None


#: 从 G-2 detail 里抽取的**可比较字段**（都是"行为可观测项"，不含 delta 幅度）。
WIRING_FIELDS: Tuple[str, ...] = (
    "applicable_windows", "fired_windows", "fired_windows_in_scope",
    "applicable_changed", "applicable_change_rate", "response_changed",
    "out_of_scope_changed", "change_matrix", "window_classes")


def compare_wiring(arms: Mapping[str, Mapping[str, Any]],
                   baseline: str = "declared") -> Dict[str, Any]:
    """比较同一触发面上**多套参数**的行为可观测项（接线证据，不是效果证据）。

    判读规则（写在产物里，避免事后解释漂移）：
      1. `fired_windows > 0` ⇒ 该触发面**到达**了候选：调整在真实评分路径上产生过非零贡献
         ⇒ "参数被解析、构造并参与打分"这条接线成立（fired_count 只在 raw ≠ 0 时自增）。
      2. 各臂之间**任一可观测项不同** ⇒ 参数的**数值**确实流进了评分。**最锐利的对照是
         "把该参数整段关掉"**：`path_log2=0 且 closer_bonus=0` 会让势差恒为 0，于是
         fired_windows 必然掉到 0——这一条能把"参数被忽略"这个解释**直接排除**；
         而只把 closer_bonus 调大/调零往往不改变计数（它只调幅度，不改是否非零）。
      3. 所有臂完全相同 ⇒ 在本口径下**不可区分**（G-2 不导出 delta 幅度），标 unresolved，
         并给出获取建议；**不得**据此写成"参数已生效 ⇒ 候选更强"。
    """

    base = arms.get(baseline) or {}
    differences: Dict[str, Any] = {}
    for label, detail in sorted(arms.items()):
        if label == baseline:
            continue
        for field in WIRING_FIELDS:
            if base.get(field) != detail.get(field):
                differences.setdefault("{0} vs {1}".format(baseline, label), {})[field] = {
                    "declared": base.get(field), label: detail.get(field)}
    coverage = {label: {"applicable_windows": (detail or {}).get("applicable_windows"),
                        "fired_windows": (detail or {}).get("fired_windows"),
                        "applicable_changed": (detail or {}).get("applicable_changed"),
                        "window_classes": (detail or {}).get("window_classes")}
                for label, detail in arms.items()}
    covered = any((detail or {}).get("fired_windows") for detail in arms.values())
    return {
        "coverage": coverage,
        "branch_reached": bool(covered),
        "differences": differences,
        "parameters_change_observable_behaviour": bool(differences),
        "verdict": (
            "触发面**到达**候选且**参数数值改变了可观测行为**：{0}".format(
                "；".join(sorted(differences))) if differences else
            ("触发面**到达**候选（fired_windows > 0 ⇒ 调整在真实评分路径上产生过非零贡献），"
             "但三套参数在 G-2 导出的可观测项上**完全相同** ⇒ 幅度层面不可区分（unresolved）"
             if covered else
             "该触发面**未到达**候选（fired_windows = 0）⇒ 本语料不含该分支的触发面，"
             "须换语料而不是加根数")),
        "boundary": "接线证据：只回答'分支是否被触发、参数是否改变分数/行为'，"
                    "**不回答**'候选是否更强'；不得据此写效果结论",
    }


def step_wiring_surface(ctx: SearchContext, *, candidate: str, verify: Mapping[str, Any],
                        wiring: Mapping[str, Any]) -> Dict[str, Any]:
    """在**规则可枚举的触发面**上核验参数接线：**不跑桌赛（0 桌）**，只跑门禁的 G-2 诊断。

    为什么这条路径优于"加根数"（Lead 裁定 2026-09-15）：2 张牌山的 0 差异很可能只是
    "该分支没被触发"。规则可枚举窗口能直接回答"分支是否被触发、参数是否改变分数"，
    而且**成本是 0 桌**、判别力还更强。

    三套参数（声明值 / 非默认值 / 零值）跑同一条 G-2 路径；**零值对照最锐利**——
    `closer_bonus=0` 会让"±closer_bonus"那部分贡献整段消失，若可观测项随之变化，
    就排除了"参数被忽略"这一解释。
    """

    step_id = "verify:wiring-surface"
    # 臂由冻结件声明：`wiring.arms`（推荐，可含"把参数整段关掉"的对照）优先；
    # 否则退回声明值/非默认值/零值三臂的旧口径。
    if isinstance(wiring.get("arms"), Mapping) and wiring["arms"]:
        arms = [(str(label), dict(weights)) for label, weights in wiring["arms"].items()]
    else:
        if not wiring.get("weights_zero"):
            raise SystemExit("冻结件缺少 verify.wiring.weights_zero：零值对照是这条路径的判别力来源")
        arms = [("declared", dict(verify.get("weights_base") or {})),
                ("injected", dict(verify.get("weights_injected") or {})),
                ("zero", dict(wiring.get("weights_zero") or {}))]
    baseline_label = str(wiring.get("baseline_label") or "declared")
    corpus = resolve_path(wiring["corpus"])
    registrations = resolve_path(wiring["registrations"])
    wall = float(wiring.get("wall_clock_sec", 1800))
    plan = ctx.step(step_id, account=ACCOUNT_SEARCH,
                    amounts={"tables": 0, "wall_clock_sec": wall},
                    note="触发面接线验证：{0} 套参数 × G-2（**0 桌**）".format(len(arms)))
    if plan["status"] == "reused":
        return {"step_id": step_id, "status": "reused"}
    reservation = plan["reservation"]
    wiring_dir = ctx.out / "verify" / "wiring"
    wiring_dir.mkdir(parents=True, exist_ok=True)
    evidence: Dict[str, Any] = {}
    tools_used: Dict[str, Any] = {}
    for label, weights in arms:
        out_path = wiring_dir / "g2-{0}.json".format(label)
        command = [tool_python(), _project_file(_PROJECT_ROOT, TOOLS_DIR / "sitin_gates.py"),
                   "--candidate", candidate, "--weights", json.dumps(weights, ensure_ascii=False),
                   "--corpus", corpus, "--registrations", registrations,
                   # **触发口径**：本步是诊断，admitted 恒为 False，不得被当成准入结论
                   "--evidence-kind", "trigger", "--out", out_path]
        run = run_tool("sitin_gates.g2-" + label, command, cwd=ctx.out,
                       timeout_sec=wall, dry_run=ctx.dry_run)
        tools_used[label] = run.to_json()
        if not ctx.dry_run:
            evidence[label] = _g2_evidence(out_path)
    if ctx.dry_run:
        ctx.ledger.release(reservation, reason="dry-run：只做计划，不执行触发面接线验证")
        print(json.dumps({"ok": True, "dry_run": True, "tables": 0}, ensure_ascii=False))
        return {"step_id": step_id, "status": "dry_run"}
    comparison = compare_wiring({label: detail for label, detail in evidence.items() if detail},
                                baseline=baseline_label)
    missing = sorted(label for label, detail in evidence.items() if not detail)
    report = {
        "schema": "sitin-wiring-verification/1",
        "generated_at_utc": utc_now(),
        "candidate": candidate,
        "corpus": str(corpus), "evidence_kind": "trigger",
        "arms": {label: {"weights": weights} for label, weights in arms},
        "tools": tools_used,
        "comparison": comparison,
        "missing_evidence": missing,
        "boundary": comparison["boundary"],
        "note": "本步不跑桌赛（0 桌）；trigger 口径下 admitted 恒为 False，"
                "因此这些记录**不能**当准入依据（与证据分级一致）",
    }
    write_json(wiring_dir / "report.json", report)
    ctx.ledger.settle(reservation, status="ok" if not missing else "failed",
                      actual={"tables": 0, "wall_clock_sec": sum(
                          float(item.get("elapsed_sec") or 0.0) for item in tools_used.values())},
                      note="触发面接线验证：{0} 套参数，缺失证据 {1} 项".format(len(arms), len(missing)))
    ctx.state.mark(step_id)
    ctx.save()
    ctx.log({"step_id": step_id,
             "status": "ok" if not missing else "failed",
             "branch_reached": comparison["branch_reached"],
             "parameters_change_observable_behaviour":
                 comparison["parameters_change_observable_behaviour"],
             "verdict": comparison["verdict"], "tables": 0, "missing": missing})
    overrun = ctx.overrun_of(step_id)
    if overrun:
        ctx.state.stop_reason = "触发面接线验证超出预留（超限即停）：{0}".format(overrun)
        ctx.state.save()
    print(json.dumps({"ok": not missing, "branch_reached": comparison["branch_reached"],
                      "parameters_change_observable_behaviour":
                          comparison["parameters_change_observable_behaviour"],
                      "tables": 0, "verdict": comparison["verdict"],
                      "report": str(wiring_dir / "report.json")}, ensure_ascii=False, indent=2))
    return {"step_id": step_id, "status": "ok" if not missing else "failed",
            "comparison": comparison}


def cmd_verify_wiring(args: Any) -> int:
    """只跑**触发面接线验证**（0 桌）：回答"分支是否被触发、参数是否改变分数"。

    与 `verify-injection` 分开成子命令的理由：表臂与触发面臂是**两条独立的账**——
    表臂在 freeze v3 里已经花过 4 桌，触发面臂在 freeze v4 里是 0 桌；混在一条命令里
    会让"预留按口径先冻结"这件事变得含糊（表臂在只给 0 桌的账里会直接撞预算）。
    """

    freeze = Freeze.load(Path(args.freeze))
    verify = freeze.data.get("verify")
    if not isinstance(verify, Mapping):
        raise SystemExit("冻结文件缺少 verify 段：核验计划必须先冻结后执行")
    wiring = verify.get("wiring")
    if not isinstance(wiring, Mapping):
        raise SystemExit("冻结文件缺少 verify.wiring 段：触发面与参数必须先冻结后执行")
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    ledger = SearchLedger.load(out / "ledger.json", freeze)
    archive = Archive.load(out / "archive.json", freeze)
    state = RunState.load(out / "state.json")
    (out / "freeze-path.txt").write_text(str(freeze.path) + "\n", encoding="utf-8")
    ctx = SearchContext(out=out, freeze=freeze, ledger=ledger, archive=archive, state=state,
                        steps_path=out / "steps.jsonl", dry_run=bool(args.dry_run),
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    outcome = step_wiring_surface(ctx, candidate=str(verify["candidate"]), verify=verify,
                                  wiring=wiring)
    ctx.save()
    ok = outcome.get("status") in ("ok", "reused", "dry_run")
    comparison = outcome.get("comparison") or {}
    print(json.dumps({"ok": ok, "status": outcome.get("status"),
                      "branch_reached": comparison.get("branch_reached"),
                      "parameters_change_observable_behaviour":
                          comparison.get("parameters_change_observable_behaviour"),
                      "verdict": comparison.get("verdict"),
                      "tables": 0,
                      "report": str(out / "verify" / "wiring" / "report.json")},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_correct(args: Any) -> int:
    """更正台账里**已知是错的**数字（不重结、不改状态，留痕）。"""

    freeze = Freeze.load(Path(args.freeze))
    out = guard_out_dir(Path(args.out))
    ledger = SearchLedger.load(out / "ledger.json", freeze)
    target = ledger.correct({"reservation_id": args.reservation_id},
                            actual={args.axis: float(args.value)}, note=args.note)
    print(json.dumps({"ok": True, "reservation_id": target["reservation_id"],
                      "charged": target["charged"], "overrun": target["overrun"],
                      "corrections": len(target.get("corrections", ()))},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: Any) -> int:
    out = guard_out_dir(Path(args.out))
    payload: Dict[str, Any] = {"out": str(out), "exists": out.is_dir()}
    for name in ("ledger.json", "archive.json", "state.json", "plan.json"):
        path = out / name
        payload[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    steps = out / "steps.jsonl"
    if steps.is_file():
        payload["steps"] = [json.loads(line) for line in
                            steps.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_freeze(args: Any) -> int:
    freeze = Freeze.load(Path(args.freeze))
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    ctx = SearchContext(out=out, freeze=freeze,
                        ledger=SearchLedger.load(out / "ledger.json", freeze),
                        archive=Archive.load(out / "archive.json", freeze),
                        state=RunState.load(out / "state.json"),
                        steps_path=out / "steps.jsonl",
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    pool = load_pool(Path(args.pool) if args.pool else None, args.candidate, args.weights)
    extra_gaps: List[Dict[str, Any]] = []
    # **知情例外进交接件**（Lead 裁定 2026-09-15 甲）：主账与并列各账的"越过已报告超限"
    # 记录逐条变成缺口条目，读者能看到"为什么一本已有超限记录的账还在继续跑"。
    for source_out in [out] + [guard_out_dir(Path(item)) for item in args.also]:
        for row in _load_overrun_acknowledgements(Path(source_out)):
            extra_gaps.append(_overrun_acknowledgement_gap(row))
    if args.stage_gap_reason:
        extra_gaps.append({"kind": "declared_gap", "impact": args.stage_gap_reason})
    ctx.legacy_wall_basis = getattr(args, "legacy_wall_basis", None)
    extra_ctxs = [load_for_report(guard_out_dir(Path(item)),
                                  legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
                  for item in args.also]
    dev_spend = None
    if args.dev_spend and Path(args.dev_spend).is_file():
        dev_spend = json.loads(Path(args.dev_spend).read_text(encoding="utf-8"))
    stage_evidence = None
    if args.stage_evidence and Path(args.stage_evidence).is_file():
        stage_evidence = json.loads(Path(args.stage_evidence).read_text(encoding="utf-8"))
    handoff = build_handoff(ctx, pool=pool, extra_gaps=extra_gaps, extra=extra_ctxs,
                            development_spend=dev_spend, stage_evidence=stage_evidence,
                            gate_dirs=getattr(args, "gate_records", None),
                            legacy_wall_basis=getattr(args, "legacy_wall_basis", None),
                            throughput_env=[Path(item) for item in
                                            (getattr(args, "throughput_env", None) or ())],
                            pre_kernel_references=_pre_kernel_references(
                                [Path(item) for item in
                                 (getattr(args, "pre_kernel_reference", None) or ())]),
                            admission_corpus=(Path(args.admission_corpus)
                                              if getattr(args, "admission_corpus", None) else None))
    write_json(out / "handoff.json", handoff)
    (out / "HANDOFF.md").write_text(render_handoff_md(handoff), encoding="utf-8")
    print(json.dumps({"ok": True, "completion_states": {
        key: value["status"] for key, value in handoff["completion_states"].items()},
        "gaps": [gap.get("kind") for gap in handoff["gaps"]]}, ensure_ascii=False, indent=2))
    return 0


def children_cpu_seconds() -> Optional[float]:
    """已结束子进程累计 CPU 秒（user+sys）。**取不到返回 None，不返回 0**。

    为什么读它：墙钟会被"同时跑了几件事"污染，CPU 秒才近似"这段代码要烧多少算力"。
    历史吞吐口径（1.468 CPU 秒/桌）就是 CPU 秒，因此对拍必须用同一个量。
    """

    try:
        import resource                       # POSIX；其它平台没有这个模块
    except Exception:                         # noqa: BLE001 —— 不支持就是取不到
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    except Exception:                         # noqa: BLE001
        return None
    return float(usage.ru_utime) + float(usage.ru_stime)


def _apply_dotted_overrides(payload: Dict[str, Any],
                            overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """按 a.b.c 路径写值（吞吐诊断靠它把"换规则版本"写成一行声明，不动别的字段）。"""

    for dotted, value in (overrides or {}).items():
        node = payload
        parts = str(dotted).split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                raise ValueError("覆盖路径 {0} 在实验配置里不存在".format(dotted))
            node = child
        node[parts[-1]] = value
    return payload


def _count_jsonl(path: Path) -> int:
    """数一个 JSONL 的行数（缺文件算 0；调用方据 problems 判定要不要停）。"""

    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


#: 吞吐归属判定的阈值（**写进报告**，读者能复核结论是不是按这个口径下的）。
THROUGHPUT_MATCH_RATIO = 1.5


def _compare_throughput(measurements: Sequence[Mapping[str, Any]],
                        reference: Mapping[str, Any]) -> Dict[str, Any]:
    """把各臂的 CPU 秒/桌与历史基准比一下，给**机械可核**的归属判定。

    判据只有一条：某臂的 CPU 秒/桌 ≤ 历史基准 × THROUGHPUT_MATCH_RATIO ⇒ 该臂与历史**同一量级**，
    差异来自该臂**没有改**的那部分配置；反之 ⇒ 该臂改掉的那一项就是成因之一。
    阈值随报告一起落盘，避免"凭感觉下结论"。
    """

    ref = reference.get("cpu_seconds_per_table")
    rows: List[Dict[str, Any]] = []
    for item in measurements:
        value = item.get("cpu_seconds_per_table")
        if ref is None or value is None:
            rows.append({"arm": item.get("arm"), "ratio_vs_reference": None,
                         "verdict": "无法判定（缺少 CPU 秒或历史基准）"})
            continue
        ratio = round(float(value) / float(ref), 4)
        rows.append({"arm": item.get("arm"), "ratio_vs_reference": ratio,
                     "verdict": ("与历史同一量级（≤ {0}×）".format(THROUGHPUT_MATCH_RATIO)
                                 if ratio <= THROUGHPUT_MATCH_RATIO else "显著变重")})
    return {"reference_cpu_seconds_per_table": ref, "threshold_ratio": THROUGHPUT_MATCH_RATIO,
            "arms": rows}


#: libproc 的 rusage 字段顺序（开头 UUID 占两个 uint64）；**只列到 cycles**，因为本工具只读这两个。
#: 与 evidence/1.2-throughput 的测量脚本同源——两边读的必须是同一组计数器，否则不可比。
_PROC_RUSAGE_FIELDS: Tuple[str, ...] = (
    "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins", "wired_size",
    "resident_size", "phys_footprint", "proc_start_abstime", "proc_exit_abstime",
    "child_user_time", "child_system_time", "child_pkg_idle_wkups", "child_interrupt_wkups",
    "child_pageins", "child_elapsed_abstime", "diskio_bytesread", "diskio_byteswritten",
    "cpu_time_qos_default", "cpu_time_qos_maintenance", "cpu_time_qos_background",
    "cpu_time_qos_utility", "cpu_time_qos_legacy", "cpu_time_qos_user_initiated",
    "cpu_time_qos_user_interactive", "billed_system_time", "serviced_system_time",
    "logical_writes", "lifetime_max_phys_footprint", "instructions", "cycles",
)


def self_cpu_seconds() -> Optional[float]:
    """本进程累计 CPU 秒（user+sys）；取不到返回 None（**不是 0**）。"""

    try:
        import resource
    except Exception:                         # noqa: BLE001
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
    except Exception:                         # noqa: BLE001
        return None
    return float(usage.ru_utime) + float(usage.ru_stime)


def self_instructions() -> Optional[float]:
    """本进程已退休的指令数（macOS 走 libproc）；**取不到就返回 None，不猜**。

    为什么值得单独读：CPU 秒会被频率与调度影响，指令数更接近"这段代码做了多少事"。
    历史测量同时记了这两项，A/B 对拍必须能给出同一组量。
    """

    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        # **缓冲区必须给足**：内核按 rusage_info_v6 的完整大小写入（128 个 uint64）。
        # 只按字段表大小分配会把栈写坏——实测直接 SIGSEGV（回合 6 第一次跑 bisect 就撞上）。
        # 诊断脚本 evidence/1.2-throughput/concurrency-checks/probe.py 用的也是 128。
        storage = (ctypes.c_uint64 * 128)()
        if lib.proc_pid_rusage(int(os.getpid()), 6, ctypes.byref(storage)) != 0:
            return None
        values = list(storage)[2:]
        index = _PROC_RUSAGE_FIELDS.index("instructions")
        if index >= len(values):
            return None
        return float(values[index])
    except Exception:                         # noqa: BLE001 —— 读不到就是不知道
        return None


def load_native_kernel(path: Path) -> Dict[str, Any]:
    """把**编译内核**换进规则层热路径；换法与 1.2 诊断脚本逐条一致（probe.py 的 --native 分支）。

    为什么在臂里显式做、而不是"装上就自动生效"：本仓库的 `_standard.py` 只在包目录里存在
    `_grouped_native<EXT_SUFFIX>` 时才加载它（那是 hatch_build/prebuilt 的**安装**路径，属构建侧动作，
    不在本包可写范围）。诊断要回答的是"这条 C 路径值多少"，所以这里按**同一条语义契约**显式换入，
    并把 `SEMANTICS_VERSION` 比对作为前置条件——版本不符直接拒绝，不做"大概一样"的替换。
    """

    import importlib.util

    from hangma_bot.hangma import _standard, hand_analysis

    spec = importlib.util.spec_from_file_location("_grouped_native", str(path))
    if spec is None or spec.loader is None:
        raise SystemExit("无法加载内核：{0}".format(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.SEMANTICS_VERSION != _standard.SEMANTICS_VERSION:
        raise SystemExit("内核语义版本不符（{0} != {1}）：拒绝替换".format(
            module.SEMANTICS_VERSION, _standard.SEMANTICS_VERSION))
    _standard.need = module.need
    _standard.cache_info = module.cache_info
    _standard.cache_clear = module.cache_clear
    _standard.NATIVE_MODULE = module
    hand_analysis._need_std = module.need
    return {"path": str(path), "semantics_version": module.SEMANTICS_VERSION,
            "native_loaded": True}

def cmd_internal_throughput_arm(args: Any) -> int:
    """内部入口：**在本地进程内**跑一臂桌赛，并把计数器写到 --counters。

    为什么必须在同一进程里跑：历史测量的 CPU 秒与指令数都是**测量进程自身**的计数器
    （probe.py 的 worker 就是 in-process 跑 run_match_experiment）。若在外部另起进程再用
    RUSAGE_CHILDREN 取，得到的是"进程树总和"，与历史口径不同量、不可直接对拍。
    """

    import runpy

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    repo_root = Path(args.repo_root)
    native_info: Dict[str, Any] = {"native_loaded": False}
    if getattr(args, "native", None):
        native_info = load_native_kernel(Path(args.native))
    # **记实际后端，而不是"有没有显式换过"**（wv16 修）：内核装好后由 _standard 在 import 期自动加载，
    # 此时 args.native 为空——旧写法会写出 native_loaded=false，与事实相反（报告说反话）。
    try:
        from hangma_bot.hangma import _standard

        info = _standard.backend_info()
        # **写者与读者用同一判据**（wv26 F2-新）：旧写法按 != "python" 判断，回退实现名
        # python_grouped 会被写进 native_loaded=true，与同一行的 fallback_reason 自相矛盾。
        native_info = _native_block_from_backend_info(info, native_info)
    except Exception as exc:                    # noqa: BLE001 —— 取不到就如实记 unknown
        native_info = dict(native_info, backend={"error": type(exc).__name__ + ": " + str(exc)},
                           native_loaded=None)
        # （native_loaded=None = "判不出来"，与 fail-closed 口径一致；不得写成 false 冒充"确认回退"）
    cpu_before, ins_before = self_cpu_seconds(), self_instructions()
    started = time.monotonic()
    cli = runpy.run_path(str(repo_root / "scripts" / "evaluate.py"))
    rc = int(cli["main"](["matches", "--experiment", str(Path(args.experiment)),
                          "--out", str(out)]) or 0)
    elapsed = time.monotonic() - started
    cpu_after, ins_after = self_cpu_seconds(), self_instructions()
    write_json(Path(args.counters), {
        "schema": "sitin-throughput-arm-counters/1",
        "repo_root": str(repo_root),
        "returncode": rc,
        "wall_seconds": round(elapsed, 4),
        "cpu_seconds": (None if cpu_before is None or cpu_after is None
                        else round(cpu_after - cpu_before, 4)),
        "instructions": (None if ins_before is None or ins_after is None
                         else int(ins_after - ins_before)),
        "native": native_info,
    })
    return rc


def _read_counters(path: Path) -> Dict[str, Any]:
    """读一臂的计数器文件；读不到返回空 dict（调用方退回 RUSAGE_CHILDREN 口径）。"""

    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:                         # noqa: BLE001 —— 读不动就是没有
        return {}
    return dict(data) if isinstance(data, Mapping) else {}

def compare_result_rows(arm_path: Path, recorded_path: Path,
                        *, key: str = "result_id") -> Dict[str, Any]:
    """把一臂的 results.jsonl 与**已落盘**的记录按 key 配对后**逐字节**比对。

    为什么按字节而不是按字段：字段级比对要先自己决定"哪些字段算数"，而等价性问题的答案
    恰恰可能是"某个我没想到的字段变了"。逐字节相等即通过；不相等时再退回去找差异字段，
    并报出**第一个不同的位置**与**不同的顶层键**，便于定位到层。
    """

    def load(path: Path) -> Dict[str, str]:
        rows: Dict[str, str] = {}
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows[str(json.loads(line).get(key))] = line
            except Exception:                   # noqa: BLE001 —— 读不动的行不参与判定
                continue
        return rows

    rows, arm_rows = load(recorded_path), load(arm_path)
    identical: List[str] = []
    mismatched: List[Dict[str, Any]] = []
    for row_key, line in sorted(arm_rows.items()):
        recorded = rows.get(row_key)
        if recorded is None:
            mismatched.append({"key": row_key, "why": "已落盘记录里没有这一行"})
            continue
        if recorded == line:
            identical.append(row_key)
            continue
        offset = next((index for index, pair in enumerate(zip(recorded, line))
                       if pair[0] != pair[1]), min(len(recorded), len(line)))
        try:
            left, right = json.loads(recorded), json.loads(line)
            differing = sorted(name for name in set(left) | set(right)
                               if left.get(name) != right.get(name))
        except Exception:                       # noqa: BLE001
            differing = []
        mismatched.append({"key": row_key, "why": "字节不同", "first_diff_at": offset,
                           "differing_fields": differing,
                           "recorded_len": len(recorded), "arm_len": len(line)})
    return {"key": key, "against": str(recorded_path), "arm_rows": len(arm_rows),
            "against_rows": len(rows), "identical_count": len(identical),
            "mismatched": mismatched,
            "all_identical": bool(arm_rows) and not mismatched,
            "scope_note": "只比对本次子集里出现的行；记录里其余行不在本次运行范围内"}

def cmd_throughput_probe(args: Any) -> int:
    """**吞吐诊断账**：把历史实验配置在当前运行时重跑，对拍 CPU 秒/桌。

    为什么单独一条命令、单独一本账：它既不是搜索也不是确认，用途是"机时报价的标定"。
    臂由冻结件声明（freeze 的 throughput_probe 段）——驱动器只按规定跑、按实结算，
    并把 **CPU 秒/桌**与**墙钟秒/桌**一起落盘：历史口径是 CPU 秒，对拍必须同量。
    """

    freeze = Freeze.load(Path(args.freeze))
    # **纯读预检**（F13）：先核墙钟基准，再写任何产物。
    freeze.wall_basis(getattr(args, "legacy_wall_basis", None))
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    (out / "freeze-path.txt").write_text(str(freeze.path) + "\n", encoding="utf-8")
    ctx = SearchContext(out=out, freeze=freeze,
                        ledger=SearchLedger.load(out / "ledger.json", freeze),
                        archive=Archive.load(out / "archive.json", freeze),
                        state=RunState.load(out / "state.json"), steps_path=out / "steps.jsonl",
                        dry_run=bool(args.dry_run),
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    # 计划来源两选一：冻结件的 throughput_probe 段（默认），或 `--plan` 指定的**已冻结计划文件**。
    # 后者用于"同一本账里做第二种诊断"——冻结件不能原地改写（sha 绑在台账上），但账本的余额可以复用；
    # 计划文件的 sha256 会写进报告，所以仍是"先冻结后执行"，不是当场编计划。
    plan_source: Dict[str, Any] = {"kind": "freeze", "path": str(freeze.path),
                                   "sha256": freeze.sha256}
    plan_data: Any = freeze.data.get("throughput_probe")
    if getattr(args, "plan", None):
        plan_path = Path(args.plan)
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        plan_source = {"kind": "plan-file", "path": str(plan_path),
                       "sha256": sha256_text(plan_path.read_text(encoding="utf-8"))}
    if not isinstance(plan_data, Mapping):
        raise SystemExit("冻结件缺少 throughput_probe 段：臂与基准参数必须**先冻结**再跑")
    base_path = resolve_path(plan_data["base_experiment"])
    arms = plan_data.get("arms") or {}
    if not arms:
        raise SystemExit("冻结件的 throughput_probe.arms 为空")
    tables_per_arm = int(plan_data["tables_per_arm"])
    tables = tables_per_arm * len(arms)
    wall_estimate = tables * ctx.wall_seconds_per_table(freeze) * WALL_SAFETY_FACTOR
    if bool(getattr(args, "rerun", False)):
        # 显式重跑：只用于"上一次标记完成、但报告里 problems 非空"（臂没产出）的情形。
        # 计费照常——**没有免费重试**；上一次若真花了产出型资源，重新预留会被账本拒绝。
        ctx.state.completed = [item for item in ctx.state.completed if item != step_id]
        ctx.state.notes.append("{0} 吞吐诊断显式重跑（--rerun）：上一次未产出可用结果".format(utc_now()))
        ctx.save()
    step_id = "probe:{0}".format(str(getattr(args, "step", None) or "throughput"))
    plan = ctx.step(step_id, account=ACCOUNT_SEARCH,
                    amounts={"tables": tables, "wall_clock_sec": wall_estimate},
                    note="吞吐诊断：{0} 臂 × {1} 桌".format(len(arms), tables_per_arm))
    if plan["status"] == "reused":
        print(json.dumps({"ok": True, "status": "reused",
                          "report": str(out / "throughput-probe.json")}, ensure_ascii=False))
        return 0
    reservation = plan["reservation"]
    base = json.loads(Path(base_path).read_text(encoding="utf-8"))
    measurements: List[Dict[str, Any]] = []
    spent_tables = 0.0
    spent_wall = 0.0
    problems: List[str] = []
    for label, overrides in arms.items():
        arm_dir = out / "arms" / str(label)
        arm_dir.mkdir(parents=True, exist_ok=True)
        # `repo_root` 是臂级声明：A/B 比"两棵代码树"时靠它指定检出点，其余键仍走点路径覆盖。
        arm_spec = dict(overrides or {})
        arm_repo_root = Path(arm_spec.pop("repo_root", str(REPO_ROOT)))
        arm_native = arm_spec.pop("native", None)
        experiment = _apply_dotted_overrides(json.loads(json.dumps(base)), arm_spec)
        experiment_path = arm_dir / "experiment.json"
        experiment_path.write_text(json.dumps(experiment, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        counters_path = arm_dir / "counters.json"
        cpu_before = children_cpu_seconds()
        # PYTHONPATH 指向该树的 src：仓库里是 editable 安装，不把它顶到前面就会
        # 用**当前**的 hangma_bot 去跑**旧**树的 scripts/evaluate.py，A/B 直接失效。
        run = run_tool("throughput.arm/" + str(label),
                       ["/usr/bin/env", "PYTHONPATH=" + str(arm_repo_root / "src"),
                        tool_python(), str(Path(__file__).resolve()),
                        "internal-throughput-arm", "--repo-root", str(arm_repo_root),
                        "--experiment", str(experiment_path), "--out", str(arm_dir),
                        "--counters", str(counters_path)]
                       + (["--native", str(arm_native)] if arm_native else []),
                       cwd=out, timeout_sec=float(plan_data.get("arm_timeout_sec") or 3600.0),
                       dry_run=ctx.dry_run)
        cpu_after = children_cpu_seconds()
        if ctx.dry_run:
            continue
        rows = _count_jsonl(arm_dir / "results.jsonl")
        counters = _read_counters(counters_path)
        cpu_sec = counters.get("cpu_seconds")
        if cpu_sec is None:
            cpu_sec = (None if cpu_before is None or cpu_after is None
                       else round(cpu_after - cpu_before, 4))
        instructions = counters.get("instructions")
        measurements.append({
            "arm": str(label), "overrides": dict(arm_spec),
            "repo_root": str(arm_repo_root),
            "native": (counters.get("native") or {"native_loaded": bool(arm_native)}),
            "tables": rows, "wall_clock_sec": round(run.elapsed_sec, 4), "cpu_sec": cpu_sec,
            "instructions": instructions,
            "wall_seconds_per_table": (round(run.elapsed_sec / rows, 4) if rows else None),
            "cpu_seconds_per_table": (round(cpu_sec / rows, 4) if rows and cpu_sec else None),
            "instructions_per_table": (int(instructions / rows) if rows and instructions else None),
            "counter_source": ("进程内计数器（与历史测量同口径）" if counters
                               else "RUSAGE_CHILDREN 增量（**口径与历史不同**，仅作兜底）"),
            "returncode": run.returncode, "timed_out": run.timed_out,
            "experiment": str(experiment_path), "results": str(arm_dir / "results.jsonl"),
        })
        spent_tables += float(rows)
        spent_wall += float(run.elapsed_sec)
        if not run.ok:
            problems.append("臂 {0} 未正常结束（退出码 {1}）".format(label, run.returncode))
        if rows != tables_per_arm:
            problems.append("臂 {0} 实跑 {1} 桌 ≠ 冻结的每臂 {2} 桌".format(
                label, rows, tables_per_arm))
    if ctx.dry_run:
        ctx.ledger.release(reservation, reason="dry-run：只做计划，不执行吞吐诊断")
        print(json.dumps({"ok": True, "dry_run": True, "planned_tables": tables},
                         ensure_ascii=False))
        return 0
    ctx.ledger.settle(reservation, status="ok" if not problems else "failed",
                      actual={"tables": min(spent_tables, float(tables)),
                              "wall_clock_sec": spent_wall},
                      note="吞吐诊断：{0} 臂实跑 {1} 桌".format(len(measurements), spent_tables))
    # **等价性比对**（可选）：把各臂结果与一份**已落盘**的记录逐字节对上，并两臂互比。
    compare_plan = plan_data.get("compare")
    equivalence = None
    if isinstance(compare_plan, Mapping) and compare_plan.get("against"):
        recorded_path = resolve_path(compare_plan["against"])
        per_arm = {item["arm"]: compare_result_rows(Path(item["results"]), recorded_path)
                   for item in measurements}
        cross = None
        if len(measurements) == 2:
            cross = compare_result_rows(Path(measurements[0]["results"]),
                                        Path(measurements[1]["results"]))
            cross["note"] = "{0} vs {1}（两臂互比）".format(measurements[0]["arm"],
                                                             measurements[1]["arm"])
        equivalence = {"recorded": str(recorded_path), "per_arm": per_arm, "arm_vs_arm": cross,
                       # **单臂也算数**：只有一臂时没有"两臂互比"可做，但"与已落盘记录逐字节相同"
                       # 本身就是等价性判据。旧写法把单臂判成"存在不一致"——机器字段说反话，
                       # 正是本包一直在消除的那类缺陷。
                       "verdict": ("全部逐字节相同"
                                   if (all(item["all_identical"] for item in per_arm.values())
                                       and (cross is None or cross["all_identical"]))
                                   else "存在不一致（见 mismatched）"),
                       "cross_arm_comparison": cross is not None}
    reference = dict(plan_data.get("archived_reference") or {})
    report = {
        "schema": "sitin-throughput-probe/1",
        "generated_at_utc": utc_now(),
        "purpose": str(plan_data.get("purpose") or "throughput_diagnosis"),
        "base_experiment": str(base_path),
        "plan": {"arms": list(arms), "tables_per_arm": tables_per_arm, "tables": tables},
        "plan_source": plan_source,
        "measurements": measurements,
        "archived_reference": reference,
        "comparison": _compare_throughput(measurements, reference),
        "equivalence": equivalence,
        "problems": problems,
        "boundary": "这是**机时标定**证据，不是任何候选的效果证据；CPU 秒取自子进程累计用量，墙钟含进程启动与落盘，两者要分开读。",
    }
    # **报告按步命名**（wv16 修）：同一本账里跑两步（如"定时代"+"等价抽查"）时，
    # 旧实现两步都写 throughput-probe.json ⇒ 后一步**静默覆盖**前一步的实测记录。
    # 步名不同的产物各自留档；同时仍写一份 latest 供"最后一步"的读者使用。
    step_report = out / "throughput-probe-{0}.json".format(str(getattr(args, "step", None) or "throughput"))
    write_json(step_report, report)
    write_json(out / "throughput-probe.json", report)
    # **只有真的跑出东西才算完成**：臂崩了/没产出时若照样标"完成"，重跑会被判 reused，
    # 操作者就只能靠换目录绕过账本——那等于让账本失去"这步到底做没做成"的信息。
    if not problems:
        ctx.state.mark(step_id)
    ctx.save()
    print(json.dumps({"ok": True, "report": str(out / "throughput-probe.json"),
                      "measurements": [{k: item[k] for k in ("arm", "tables",
                                        "wall_seconds_per_table", "cpu_seconds_per_table")}
                                       for item in measurements],
                      "remaining_tables": ctx.ledger.remaining(ACCOUNT_SEARCH)["tables"]},
                     ensure_ascii=False, indent=2))
    return 0 if not problems else 1

def cmd_probe_stage(args: Any) -> int:
    freeze = Freeze.load(Path(args.freeze))
    out = guard_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)
    ctx = SearchContext(out=out, freeze=freeze,
                        ledger=SearchLedger.load(out / "ledger.json", freeze),
                        archive=Archive.load(out / "archive.json", freeze),
                        state=RunState.load(out / "state.json"),
                        steps_path=out / "steps.jsonl",
                        legacy_wall_basis=getattr(args, "legacy_wall_basis", None))
    probe = stage_seating_probe(ctx, candidate_policy=args.candidate)
    write_json(out / "stage-panel-probe.json", probe)
    print(json.dumps({"verdict": probe["verdict"], "whitelist": probe["whitelist"],
                      "returncode": probe["tool"]["returncode"]}, ensure_ascii=False))
    return 0 if probe["verdict"] == "supported" else 1


# ============================================================ 9. action_value_v1 搜索路线
#
# §9.4 固定迭代顺序落账、§13.1 七命令路由、T17 四类账目与全机 12 工作进程
# 上限。本节不改旧 delta 路径任何语义：新路线阶段推进**不读** resolved_positive
# （旧 describe_statistics/阶段规则原义不动）；旧 SearchLedger.confirm 硬禁
# 继承到新账本（无显式确认授权时任何 confirm 记账直接拒绝）。
# 零预算红线：无授权时全部命令对真实桌赛/LLM 调用 fail-closed——面板用
# C1 scripted_fixture（真实桌赛实例恒 0），生成用离线 mock（不调真实 LLM，
# 不读 .private/sitin-llm.json）。
# ============================================================

#: 新路线 schema 常量（独立记录文件，不与旧 search schema 混写）。
AV_ROUTE_SCHEMA = "sitin-action-value-route/1"
AV_ITERATION_SCHEMA = "sitin-action-value-iteration/1"
AV_LEDGER_SCHEMA = "sitin-action-value-ledger/1"
AV_EVALUATION_SCHEMA = "sitin-action-value-evaluation/1"
#: 与 sitin_gates.AV_MAX_WORKERS 同一常量（两处一致由 validate-contract 对账）。
AV_MAX_WORKERS = 12
#: 确认预算默认值（§11：单列、默认继承原值 0，不从开发额度划拨）。
AV_CONFIRM_DEFAULT_BUDGET = 0.0
#: 基线身份（V2 固定对照；夹具续打以行为策略站立，identity 仍记 V2 基线）。
AV_BASELINE_ID = "v2-baseline-frozen"
#: A1 修复：条件面板的冻结规则版本与每桌单局数（与 av build_panel 调用同口径；
#: 供状态机/CLI 在**组合处**装配真实运行时时构造 TournamentConfig）。
AV_CONDITIONAL_RULESET_VERSION = "v26"
AV_CONDITIONAL_ROUNDS_PER_GAME = 8

#: §9.4 一次迭代的固定顺序（落账以此为准；乱序/缺步即迭代记录不完整）。
AV_ITERATION_ORDER = (
    "read_budget_and_reserve",
    "select_operator_and_generate",
    "supervised_load_and_admission",
    "behavior_panel_coverage",
    "opportunity_and_normal_panels",
    "root_paired_statistics",
    "three_segment_feedback",
    "archive_update",
    "atomic_save_and_ledger",
)

#: T17 四类账目（+确认预留单列）：token 输入/输出、桌赛实例完整/部分、
#: 前缀生成成本、确认预留。reserve 先落盘后执行；confirm 无授权硬禁。
AV_LEDGER_ACCOUNTS = (
    "tokens_input", "tokens_output", "tables_full", "tables_partial",
    "prefix_generation", "confirm_reserved",
)


def av_gates():
    """门禁模块（同目录 sibling；admit/load/身份核验单一来源）。"""

    return _sibling("sitin_gates")


def av_opportunities():
    """C1 面板模块（双臂/快照/费用账单一来源）。"""

    return _sibling("sitin_opportunities")


def av_natural_panel():
    """自然面板模块（同目录工具）：补根与自然面板步共用**同一份**真实执行装配。"""

    return _sibling("sitin_natural_panel")


def av_archive():
    """C2 统计/档案/调度模块（statistics/update-archive/next-plan/nominate）。"""

    return _sibling("sitin_archive")


def av_stage():
    """目标求值模块（group_advance_v1 的识别区间算法单一来源）。"""

    return _sibling("sitin_stage")


def av_generate():
    """生成模块（TaskContract 渲染与静态预检单一来源）。"""

    return _sibling("sitin_generate")


def av_feedback():
    """三段反馈模块（R7/P9：事实/关联结果的**唯一**程序化投影来源）。

    主状态机的 summary 步与 CLI 都走这一份实现，避免"两套反馈读同一产物却读错
    层级"（复审 §4 A5：旧的自建反馈把 null 渲染进 M1 提示词，模型据此改动）。
    """

    return _sibling("sitin_feedback")


class WorkerCapExceeded(RuntimeError):
    """全机工作进程上限（12）的调度请求被拒绝（T17）。"""


class LedgerAmountInvalid(ValueError):
    """账本金额非法（负数/NaN/±Inf）：记账前校验，拒绝写坏账。"""


class LedgerUnauthorized(RuntimeError):
    """账户未声明授权额度仍试图记正数账：fail-closed，不无限额记账。"""


class LedgerOverAuthorized(RuntimeError):
    """按授权总额扣除已结算+在途预留后超额：预留被拒（Q3，不超限执行）。"""


class DuplicateReservation(RuntimeError):
    """同 step_id/账户/金额的在途预留重复提交：拒绝双计，恢复走 settle。"""


def av_ledger_budgets_from_authorization(
        authorization: Optional[Mapping[str, Any]]) -> Optional[Dict[str, float]]:
    """从授权令牌读开发账户授权额度。

    两种形态都认（Q6：新形态 sitin-authorization/1 的 allowed_accounts，legacy 的
    budgets）——**新形态优先**：同一个文件两者都给时以新形态为准（不静默按旧键少算
    或多算）。无额度表返回 None（调用方 fail-closed：正数记账将拒绝）。confirm 额度
    单列（confirm_authorized_budget 参数），不混入开发 budgets。
    """
    if not isinstance(authorization, Mapping):
        return None
    budgets = authorization.get("allowed_accounts")
    if not isinstance(budgets, Mapping):
        budgets = authorization.get("budgets")
    if not isinstance(budgets, Mapping):
        return None
    out: Dict[str, float] = {}
    for account in AV_LEDGER_ACCOUNTS:
        value = budgets.get(account)
        if isinstance(value, (int, float)) and not isinstance(value, bool) \
                and math.isfinite(float(value)) and float(value) >= 0:
            out[account] = float(value)
    return out


def av_generation_call_limits_from_authorization(
        authorization: Optional[Mapping[str, Any]]) -> Optional[Dict[str, float]]:
    """读取可选的单次生成 token 上界；缺省沿用历史预留口径。

    这是一次调用的实际输入/输出容量声明，不是账户总预算。只要该块存在，两个
    维度必须同时为正有限数；不能把 bool、零或半份声明当作可安全降级的默认值。
    """
    if not isinstance(authorization, Mapping) or "generation_call_limits" not in authorization:
        return None
    limits = authorization.get("generation_call_limits")
    if not isinstance(limits, Mapping):
        raise ValueError("generation_call_limits 必须是含 tokens_input/tokens_output 的映射")
    out: Dict[str, float] = {}
    for account in ("tokens_input", "tokens_output"):
        value = limits.get(account)
        if not (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)) and float(value) > 0):
            raise ValueError(
                "generation_call_limits.{0} 必须是正有限数（非 bool），得到 {1!r}"
                .format(account, value))
        out[account] = float(value)
    return out


#: Q6：三个真实执行入口的**操作标签**与最小账户需求（统一校验的调用面）。
#: 语义要说清：这里是"该操作至少要有一个可执行的额度单位，且账户必须已声明"这一层
#: （未声明 = 不当作无限额，见 av_authorization_check）；**逐次执行的总额上限仍由
#: 共享账本的"先预留后执行"拒绝**（LedgerOverAuthorized，不超限执行）——两者不互相
#: 替代：本项挡住"拿错批次/越权操作/未声明账户"，账本挡住"总额超限"。
AV_AUTHORIZATION_OPERATION_REQUIREMENTS: Dict[str, Dict[str, float]] = {
    "natural_panel": {"tables_full": 1.0},
    "conditional_prefix": {"prefix_generation": 1.0},
    "conditional_refill": {"tables_full": 1.0},
    "family_fill": {"tables_full": 1.0},
    "evaluate": {},
    "summarize": {},
}


def av_authorization_audit(
    authorization: Optional[Mapping[str, Any]], *, operation: str,
    required: Optional[Mapping[str, float]] = None,
    expected_batch_label: Optional[str] = None,
    expected_authorization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """统一**受信**授权校验（Q6）：转发到坐落在 sitin_opportunities 的**唯一实现**。

    为什么落一个转发而不是各步各写：旧实现把 "authorized is True and batch == 7"
    抄在三处（自然面板 / 补根 / 家族补根），只认一个历史门值——不校验批次标签、
    不校验操作是否在允许集内、不校验账户是否已声明；三份拷贝还会各自漂移。
    """

    return av_opportunities().av_authorization_check(
        authorization, operation=operation, required=required,
        expected_batch_label=expected_batch_label,
        expected_authorization_id=expected_authorization_id)


def av_authorization_stamp(authorization: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """授权文件盖上形态标签（P2：authorization_form 写进授权文件；legacy 显式标注）。"""

    return av_opportunities().av_authorization_stamp(authorization)


def av_authorization_archive_entry(
    authorization: Optional[Mapping[str, Any]], *, operation: str,
    required: Optional[Mapping[str, float]] = None,
    expected_batch_label: Optional[str] = None,
    expected_authorization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """授权档案条目（P2：authorization-archive.json 读这些字段）。"""

    return av_opportunities().av_authorization_archive_entry(
        authorization, operation=operation, required=required,
        expected_batch_label=expected_batch_label,
        expected_authorization_id=expected_authorization_id)


def av_authorization_allows(
    authorization: Optional[Mapping[str, Any]], *, operation: str,
    required: Optional[Mapping[str, float]] = None,
    expected_batch_label: Optional[str] = None,
    expected_authorization_id: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """统一校验的判据形态：(是否放行, 具名拒绝原文, 审计记录)。

    失败关闭：任何问题项都返回 False —— 调用方据此**不动一张桌**，并把审计记录
    （authorization_form / authorization_id / batch_label / allowed_operations /
    allowed_accounts / problems）原样写进 state 与事务件。
    """

    verdict = av_authorization_audit(
        authorization, operation=operation, required=required,
        expected_batch_label=expected_batch_label,
        expected_authorization_id=expected_authorization_id)
    ok = bool(verdict.get("ok"))
    reason = "" if ok else av_opportunities().av_authorization_refusal(verdict)
    return ok, reason, verdict


# ===========================================================================
# S2/S3（R7 修复）· 恢复身份核验与副作用事务检查点的共用原语
#
# 复审 §3 S2（P1）：恢复入口的 identity 核验是**可选**的，只比较调用方给定字段，
# 开轮时算的摘要没有作为门槛；**每个推进/恢复入口必须自行重算冻结清单**
# （见 av_frozen_manifest / av_verify_run_identity），调用方材料只作额外期望。
# 复审 §3 S3（P1）：H/M 顺序执行而状态只在整步结束才保存、已结算任务可再次预留、
# 账本原地覆盖写、transactions/ 文件不参与对账——本节给出实例任务台账、
# 恢复对账、单推进者锁与账本互斥原子落盘的原语。
# ===========================================================================


class AdvancerBusy(RuntimeError):
    """运行目录已有推进者：同一运行目录同时只允许一个推进者（S3）。"""


class TaskAlreadySettled(RuntimeError):
    """同 step/账户的任务已结算：不得原地再次预留（S3：已结算任务再次预留=重复计费）。

    失败/中断后的重试必须由恢复对账显式 supersede 让位，费用保留，不静默双计。
    """


#: 家族评价/补根路径必须转成**失败返回**的账本异常（R9/P8，关口二 run2）。
#:
#: 账本拒绝与任务状态冲突是**运行面**的异常，不是"补根不会失败"的理由：按设计 §9.2，
#: 补根失败要保持原家族席与原 epoch（不混新旧均值）、挑战者留候选池，并把停因写清楚。
#: 抛穿 worker 会同时丢掉这三样（run2：`TaskAlreadySettled` 抛穿 `_step_refresh_fill`，
#: worker 退出码 3）。本元组只收**账本语义**异常，不收 OSError/KeyError 之类的实现缺陷。
AV_LEDGER_FAILURE_ERRORS: Tuple[type, ...] = (
    BudgetExhausted, LedgerUnauthorized, LedgerOverAuthorized, TaskAlreadySettled,
    DuplicateReservation, ConfirmAccountFrozen, LedgerAmountInvalid,
)


class IdentityRefused(RuntimeError):
    """恢复身份核验未通过（S2）：依赖/候选/面板/合同变化使旧结果失效，拒绝续写。"""


def av_atomic_write_bytes(path: Path, data: bytes) -> None:
    """原子落盘：同目录临时文件 + fsync + os.replace（中断不产生半截文件）。

    S3：账本、状态、实例台账、检查点一律经本入口落盘——进程在写入中途被杀时，
    主文件要么是旧的完整版本、要么是新的完整版本，不会被写成半截 JSON。
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-{0}".format(uuid.uuid4().hex[:8]))
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def av_fault_point(name: str, **fields: Any) -> None:
    """故障注入点（S3 验收用）：默认空实现；测试/演练替换本函数即可注入中断。

    注入点命名 <面板>:<混合>:<阶段>（如 natural:H:after_result_before_settle）
    或 generate:after_ingest_before_state_save——覆盖"结果写入与费用结算之间"、
    "账本写入中断"、"回复已存在但生成状态未提交"等窗口。
    """

    return None


def av_advancer_lock_path(run_root: Path) -> Path:
    """运行目录的推进者锁文件（S3：一个运行目录只有一个推进者）。"""

    return Path(run_root) / "advance.lock"


@contextmanager
def av_advancer_lock(run_root: Path):
    """取得运行目录推进权（flock 独占、非阻塞）；已有推进者即 AdvancerBusy。"""

    path = av_advancer_lock_path(run_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AdvancerBusy(
                "本运行目录已有推进者（锁 {0}）：同一运行目录同时只允许一个推进者，"
                "第二个恢复者被拒；等其结束或确认其已死后重试（S3）".format(
                    path.name)) from error
        yield {"lock_path": str(path)}
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def av_ledger_rows_for_step(ledger: "ActionValueLedger", *, step_prefix: str,
                            account: Optional[str] = None) -> List[Dict[str, Any]]:
    """一段 step 前缀下的账行（恢复对账的匹配面）。"""

    rows = [item for item in ledger.reservations
            if str(item.get("step_id") or "").startswith(str(step_prefix))]
    if account is not None:
        rows = [item for item in rows if item.get("account") == account]
    return rows


def av_reconcile_ledger_attempts(ledger: "ActionValueLedger", *, step_prefix: str,
                                 account: str = "tables_full",
                                 result_available: bool = False,
                                 executed: Optional[float] = None,
                                 reason: str = "") -> Dict[str, Any]:
    """恢复先对账：把一段 step 前缀下的旧尝试账行处理干净（S3）。

    - **在途（reserved）**：结算。结果可用时按结果记录的执行数结算（精确），
      否则**保守按预留额**结算（usage 未知不得下调，失败成本保留），
      不留"卡在旧预留"的行；
    - **已结算且结果不可用**：标记 superseded 让出 step_id 给新尝试
      （费用保留；不原地重复预留，也不静默丢结果）。
    """

    rows = av_ledger_rows_for_step(ledger, step_prefix=step_prefix, account=account)
    settled: List[str] = []
    superseded: List[str] = []
    for row in rows:
        if row["status"] == "reserved":
            exact = bool(result_available and executed is not None)
            ledger.settle(
                row, actual=(float(executed) if exact else float(row["amount"])),
                note="恢复对账（{0}）：中断的在途预留按{1}结算，失败成本保留".format(
                    reason or step_prefix, "结果记录的执行数" if exact else "预留额（保守）"))
            settled.append(str(row["reservation_id"]))
            if not result_available:
                # 结果不可用：结算后立即让出 step_id 给新尝试（费用保留）。
                ledger.supersede(
                    step_id=str(row["step_id"]), account=account,
                    reason="恢复对账：{0}（中断尝试已保守结算，让位给新尝试）".format(
                        reason or step_prefix))
                superseded.append(str(row["reservation_id"]))
        elif row["status"] == "settled" and not row.get("superseded") \
                and not result_available:
            # 费用已结算但结果缺失：新尝试需要同一个 step_id → 显式让位（费用不动）。
            ledger.supersede(step_id=str(row["step_id"]), account=account,
                             reason="恢复对账：{0}（结果缺失，让位给新尝试，费用保留）".format(
                                 reason or step_prefix))
            superseded.append(str(row["reservation_id"]))
    return {"step_prefix": step_prefix, "rows": len(rows),
            "settled": settled, "superseded": superseded}


class ActionValueLedger:
    """action_value_v1 路线台账（T17；Q3 加固）：限额强制 + 共享工作租约。

    与旧 SearchLedger 同一纪律：先预留后执行、失败同样计费、confirm 硬禁
    （确认额度默认 0，无显式授权文件不得动用——授权文件须含
    confirm_budget>0 且 authorized=true）。

    Q3 加固（REVIEW-V4 Q3）：
    - **限额强制**：reserve 前校验金额为非负有限数；正数记账必须在授权总额内
      ——按"授权额度 −（已结算 + 在途预留）"校验，超限即拒（LedgerOverAuthorized）；
      未声明授权额度的账户记正数账即拒（LedgerUnauthorized，fail-closed）。
      amount=0 的纯登记行不受限额约束（不占额度）。
    - **重复预留拒绝**：同 step_id/账户/金额的在途预留重复提交即拒
      （DuplicateReservation），恢复路径是对原预留 settle。
    - **usage 未知保守预留**：settle(usage_unknown=True) 且无 actual 时按预留额
      计费不下调（保守），行内标 usage_unknown=True。
    - **全机工作租约**：worker 计数存共享租约文件（账本同目录 *.workers.json），
      跨进程用 flock 互斥——对象内变量不作全机上限依据。
    """

    #: 台账 schema。
    SCHEMA = AV_LEDGER_SCHEMA

    def __init__(self, path: Path, *, confirm_authorized_budget: float = 0.0,
                 authorized_budgets: Optional[Mapping[str, float]] = None) -> None:
        self.path = Path(path)
        self.confirm_authorized_budget = float(confirm_authorized_budget)
        self.reservations: List[Dict[str, Any]] = []
        self.authorized_budgets: Dict[str, float] = {}
        if authorized_budgets:
            for account, value in authorized_budgets.items():
                if account not in AV_LEDGER_ACCOUNTS:
                    raise ValueError("授权额度含未知账户 {0!r}".format(account))
                if not (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and math.isfinite(float(value)) and float(value) >= 0):
                    raise LedgerAmountInvalid(
                        "授权额度 {0}={1!r} 必须是非负有限数".format(account, value))
                self.authorized_budgets[account] = float(value)

    # —— 限额视图 ——
    def authorized_total(self, account: str) -> Optional[float]:
        """账户授权总额；confirm_reserved 用 confirm_authorized_budget，其余用
        authorized_budgets；未声明返回 None（正数记账将 fail-closed）。"""
        if account == "confirm_reserved":
            return self.confirm_authorized_budget
        return self.authorized_budgets.get(account)

    # —— 账目视图 ——
    def spent(self, account: str) -> float:
        if account not in AV_LEDGER_ACCOUNTS:
            raise ValueError("未知账目 {0!r}（允许：{1}）".format(account, AV_LEDGER_ACCOUNTS))
        return round(sum(float(item["charged"]) for item in self.reservations
                         if item["account"] == account
                         and item["status"] in ("settled", "reserved")), 6)

    def remaining(self, account: str) -> Optional[float]:
        """授权余额 = 授权总额 −（已结算 + 在途预留）；未声明授权为 None。"""
        total = self.authorized_total(account)
        if total is None:
            return None
        return round(total - self.spent(account), 6)

    def account_summary(self) -> Dict[str, float]:
        return {account: self.spent(account) for account in AV_LEDGER_ACCOUNTS}

    # —— 记账动作 ——
    def reserve(self, *, step_id: str, account: str, amount: float, note: str = "",
                usage_unknown: bool = False) -> Dict[str, Any]:
        # S3：读改写互斥 + 落盘前重读（跨进程不丢他方写入），再校验限额。
        with self._exclusive():
            return self._reserve_locked(step_id=step_id, account=account,
                                        amount=amount, note=note,
                                        usage_unknown=usage_unknown)

    def _reserve_locked(self, *, step_id: str, account: str, amount: float,
                        note: str, usage_unknown: bool, persist: bool = True) -> Dict[str, Any]:
        if account not in AV_LEDGER_ACCOUNTS:
            raise ValueError("未知账目 {0!r}".format(account))
        if not (isinstance(amount, (int, float)) and not isinstance(amount, bool)
                and math.isfinite(float(amount)) and float(amount) >= 0):
            raise LedgerAmountInvalid(
                "预留金额必须是非负有限数，得到 {0!r}（步 {1}）".format(amount, step_id))
        if account == "confirm_reserved" and self.confirm_authorized_budget <= 0:
            raise ConfirmAccountFrozen(
                "确认预算默认 0 且硬禁继承（步 {0}）：确认额度单列，不从开发额度"
                "划拨；需显式授权文件（confirm_budget>0 且 authorized=true）".format(step_id))
        if float(amount) > 0:
            total = self.authorized_total(account)
            if total is None:
                raise LedgerUnauthorized(
                    "账户 {0} 未声明授权额度（步 {1}）：fail-closed，正数记账拒绝——"
                    "在授权令牌 budgets 或 ActionValueLedger(authorized_budgets=...) "
                    "声明额度后再记账（Q3）".format(account, step_id))
            committed = self.spent(account)
            if committed + float(amount) > total + 1e-9:
                raise LedgerOverAuthorized(
                    "预留被拒（步 {0}）：授权总额 {1} −（已结算+在途预留）{2} 后不足以"
                    "再预留 {3}（Q3：按授权总额扣除已结算+在途预留，超限即拒）".format(
                        step_id, total, committed, float(amount)))
        for item in self.reservations:
            if item["account"] != account or item["step_id"] != step_id:
                continue
            if item["status"] == "reserved":
                raise DuplicateReservation(
                    "重复预留被拒（步 {0}/{1}/{2}）：在途预留 {3} 已存在；恢复应对其 "
                    "settle，不得双计（Q3）".format(step_id, account, float(amount),
                                                    item["reservation_id"]))
            if item["status"] == "settled" and not item.get("superseded"):
                # S3：失败/中断后的重试必须经恢复对账 supersede 显式让位（费用保留），
                # 不允许"同一任务在原地再预留一次"——那是重复计费。
                raise TaskAlreadySettled(
                    "已结算任务不得再次预留（步 {0}/{1}，已结算行 {2}）：中断后的新尝试 "
                    "必须由恢复对账 supersede 让出 step_id（失败成本保留）后再预留"
                    "（S3）".format(step_id, account, item["reservation_id"]))
        reservation = {
            "reservation_id": "{0}#{1}".format(step_id, len(self.reservations) + 1),
            "step_id": step_id, "account": account, "amount": float(amount),
            "note": note, "at_utc": utc_now(), "status": "reserved",
            "charged": float(amount), "usage_unknown": bool(usage_unknown),
        }
        self.reservations.append(reservation)
        if persist:
            self.save()
        return reservation

    def settle(self, reservation: Mapping[str, Any], *, status: str = "settled",
               actual: Optional[float] = None, note: str = "",
               usage_unknown: bool = False) -> None:
        with self._exclusive():
            self._settle_locked(reservation, status=status, actual=actual,
                                note=note, usage_unknown=usage_unknown)

    def _settle_locked(self, reservation: Mapping[str, Any], *, status: str,
                       actual: Optional[float], note: str,
                       usage_unknown: bool) -> None:
        if actual is not None and not (isinstance(actual, (int, float))
                                       and not isinstance(actual, bool)
                                       and math.isfinite(float(actual))
                                       and float(actual) >= 0):
            raise LedgerAmountInvalid(
                "结算金额必须是非负有限数，得到 {0!r}".format(actual))
        for item in self.reservations:
            if item["reservation_id"] == reservation["reservation_id"]:
                item["status"] = status
                # usage 未知 + 无实际值：保守按预留额计费（不下调），行内标未知。
                if actual is not None:
                    item["charged"] = float(actual)
                elif usage_unknown:
                    item["usage_unknown"] = True
                if usage_unknown:
                    item["usage_unknown"] = True
                if note:
                    item["note"] = "{0}；{1}".format(item.get("note", ""), note)
                break
        else:
            raise KeyError("未知预留 {0}".format(reservation["reservation_id"]))
        self.save()

    def supersede(self, *, step_id: str, account: str, reason: str) -> Dict[str, Any]:
        """让出 step_id：把已结算的旧尝试行标记 superseded（费用不动）。

        S3：只有恢复对账在"费用已结算但结果缺失、需要新尝试"时调用；被让位的行
        保留金额并记原因，供事后核对"失败成本保留"。返回最后被让位的行。
        """

        with self._exclusive():
            changed: Optional[Dict[str, Any]] = None
            for item in self.reservations:
                if item["account"] != account or item["step_id"] != step_id:
                    continue
                if item["status"] != "settled" or item.get("superseded"):
                    continue
                item["superseded"] = True
                item["superseded_reason"] = str(reason)
                item["superseded_at_utc"] = utc_now()
                changed = item
            if changed is None:
                raise KeyError("没有可让位的已结算行（步 {0}/{1}）".format(
                    step_id, account))
            self.save()
            return dict(changed)

    # —— 账本读改写互斥与原子落盘（S3）——
    @property
    def ledger_lock_path(self) -> Path:
        return self.path.parent / (self.path.name + ".lock")

    def _reload_from_disk(self) -> None:
        """落盘前重读账本：跨进程读改写互斥时不得用旧内存快照覆盖他方写入。"""

        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "账本文件不可解析，拒绝在其上继续记账（fail-closed）：{0}: {1}".format(
                    self.path, error)) from error
        if not isinstance(data, Mapping) or not isinstance(
                data.get("reservations"), list):
            raise RuntimeError("账本文件结构非法，拒绝在其上继续记账：{0}".format(
                               self.path))
        self.reservations = list(data.get("reservations") or [])

    @contextmanager
    def _exclusive(self):
        """账本读改写互斥（跨进程 flock）+ 重读；save() 不在此内部再取锁。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                self._reload_from_disk()
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    # —— 全机工作进程上限（T17：12；13 个请求拒绝）——
    # Q3 加固：计数持久化在共享租约文件（账本同目录 *.workers.json），跨进程
    # flock 互斥；对象内变量不作全机上限依据。
    @property
    def worker_lease_path(self) -> Path:
        return self.path.parent / (self.path.name + ".workers.json")

    @property
    def _worker_lock_path(self) -> Path:
        return self.path.parent / (self.path.name + ".workers.lock")

    def _read_worker_lease(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.worker_lease_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"active": 0, "holders": []}
        if not isinstance(data, Mapping):
            return {"active": 0, "holders": []}
        return {"active": int(data.get("active") or 0),
                "holders": list(data.get("holders") or [])}

    def _write_worker_lease(self, lease: Mapping[str, Any]) -> None:
        self.worker_lease_path.parent.mkdir(parents=True, exist_ok=True)
        self.worker_lease_path.write_text(
            json.dumps(lease, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")

    def request_workers(self, count: int, *, purpose: str = "") -> None:
        count = int(count)
        if count < 0:
            raise ValueError("工作进程数必须非负，得到 {0}".format(count))
        self._worker_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._worker_lock_path.open("a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                lease = self._read_worker_lease()
                if lease["active"] + count > AV_MAX_WORKERS:
                    raise WorkerCapExceeded(
                        "工作进程请求被拒绝：在册 {0} + 请求 {1} 超过全机上限 {2}（{3}）"
                        "[共享租约 {4}]".format(lease["active"], count, AV_MAX_WORKERS,
                                                purpose or "未注明用途",
                                                self.worker_lease_path.name))
                lease["active"] = lease["active"] + count
                if purpose:
                    lease["holders"] = sorted(set(lease["holders"]) | {str(purpose)})
                self._write_worker_lease(lease)
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def release_workers(self, count: int) -> None:
        count = int(count)
        if count < 0:
            raise ValueError("工作进程数必须非负，得到 {0}".format(count))
        self._worker_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._worker_lock_path.open("a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                lease = self._read_worker_lease()
                lease["active"] = max(0, lease["active"] - count)
                self._write_worker_lease(lease)
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    @property
    def workers_active(self) -> int:
        return self._read_worker_lease()["active"]

    def to_json(self) -> Dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "accounts": list(AV_LEDGER_ACCOUNTS),
            "spent": self.account_summary(),
            "confirm_authorized_budget": self.confirm_authorized_budget,
            "authorized_budgets": dict(self.authorized_budgets),
            "confirm_policy": "confirm 硬禁继承现状：默认 0，无显式授权任何 confirm 记账拒绝",
            "limit_policy": "Q3：正数记账须在授权总额内（扣已结算+在途预留）；"
                            "未声明额度 fail-closed 拒绝；amount=0 纯登记不限额",
            "reservations": self.reservations,
            "workers_active": self.workers_active,
            "worker_lease": self.worker_lease_path.name,
            "worker_cap": AV_MAX_WORKERS,
        }

    def save(self) -> None:
        # S3：原子落盘（tmp + fsync + rename）——中断不产生半截账本。
        av_atomic_write_bytes(
            self.path,
            (json.dumps(self.to_json(), ensure_ascii=False, indent=2)
             + "\n").encode("utf-8"))

    @classmethod
    def load(cls, path: Path, *, confirm_authorized_budget: Optional[float] = None,
             authorized_budgets: Optional[Mapping[str, float]] = None) -> "ActionValueLedger":
        """回读台账；授权额度取"文件与参数的较小者"（不许回读抬高限额）。"""
        file_budgets: Dict[str, float] = {}
        file_confirm: Optional[float] = None
        if Path(path).is_file():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for account, value in (data.get("authorized_budgets") or {}).items():
                if account in AV_LEDGER_ACCOUNTS and isinstance(value, (int, float)) \
                        and not isinstance(value, bool) and math.isfinite(float(value)):
                    file_budgets[account] = float(value)
            if isinstance(data.get("confirm_authorized_budget"), (int, float)) \
                    and not isinstance(data.get("confirm_authorized_budget"), bool):
                file_confirm = float(data["confirm_authorized_budget"])
        merged_budgets: Optional[Dict[str, float]] = None
        if authorized_budgets is not None or file_budgets:
            merged_budgets = dict(file_budgets)
            for account, value in (authorized_budgets or {}).items():
                merged_budgets[account] = min(float(value),
                                              merged_budgets.get(account, float(value)))
        confirm = (file_confirm if file_confirm is not None else 0.0) \
            if confirm_authorized_budget is None \
            else float(confirm_authorized_budget)
        ledger = cls(Path(path), confirm_authorized_budget=confirm,
                     authorized_budgets=merged_budgets)
        if Path(path).is_file():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            ledger.reservations = list(data.get("reservations") or [])
        return ledger


# ===========================================================================
# S2 · 冻结清单（恢复身份）：入口自算，覆盖传递依赖
# ===========================================================================

#: 冻结清单 schema（开轮冻结、每个推进/恢复入口重算比对）。
#: N4：/2 起摘要吃**完整规范化依赖清单**（面 + 传递闭包明细 + 工具/合同文件 +
#: 基线传递闭包），不再只吃 surfaces——旧版本状态一律拒绝恢复（身份口径已变）。
#: S2/P3：/3 起摘要再吃**入口调用图**（真实装配入口 → 桌赛驱动 / 组合根 / 同目录
#: 工具模块的传递闭包）。/2 的漏项是「工具文件只哈希自身」：`sitin_natural_panel.py`
#: 进清单，它真正调用的 `hangma_bot.offline.evaluate.drive_match` 与
#: `hangma_bot.bootstrap.build_evaluation_runtime` 不进任何摘要面，于是纯内存改
#: 一个方法体（只编译、从不执行）也能复用旧结果。身份口径已变 ⇒ 旧状态一律拒绝恢复。
#: S2/P7：/4 起摘要再吃**家族通道接线声明**（`family_channel` + `family_refresh`）。
#: /3 的漏项是「计划里的通道配置不进任何面」：机器实测同一计划下 family_channel
#: 有/无、刷新声明有/无，冻结摘要**逐字相同** ⇒ 两次只差家族接线配置的运行拿到
#: 同一身份，旧结果被跨配置复用（R9 §14.3「未解释身份冲突」）。身份口径已变 ⇒
#: 旧状态（含 /3）一律拒绝恢复。
AV_FROZEN_MANIFEST_SCHEMA = "sitin-action-value-frozen-manifest/4"
#: 冻结清单覆盖的面（复审 §3 S2 逐项 + P3 入口调用图 + P7 家族通道声明）；候选面由
#: 入口重算 candidate_id 单独核验。
AV_FROZEN_MANIFEST_SURFACES: Tuple[str, ...] = (
    "rules", "projection", "executor", "simulator", "statistics",
    "baseline", "opponent", "analysis_config", "panel", "root_purpose",
    "entry_graph", "family_channel", "family_refresh",
)
#: 摘要除此之外还必须吃下的**全局段**（N4：面之外仍影响执行的登记依赖）。
#: 缺了它们就会出现「清单明细里看得到文件名、摘要却不变」的假身份。
AV_FROZEN_MANIFEST_SECTIONS: Tuple[str, ...] = AV_FROZEN_MANIFEST_SURFACES + (
    "module_closure", "baseline_module_closure", "tool_files", "contract_files",
    "missing_modules", "baseline_missing_modules", "roots", "schema",
    "entry_files", "entry_module_closure", "entry_tool_closure", "entry_edges",
    "entry_missing", "entry_coverage_gaps",
)
#: 传递闭包的额外根：规则引擎与模拟器组合根（第一方身份清单之外的传递起点）。
AV_MANIFEST_ROOT_MODULES: Tuple[str, ...] = (
    "hangma_bot.hangma.engine",
    "hangma_bot.simulation.engine",
    "hangma_bot.simulation.identity",
    "hangma_bot.simulation.projection",
)
#: 一并纳入身份的编排侧工具（同目录；改哪一份都改变运行身份）。
#:
#: S2/P3：不再手写名单——由 `sitin_deps.ENTRY_FILES`（编排状态机 + 桌赛执行件 +
#: 全部**已登记**的动态 sibling + 登记表自身）派生。手写名单与动态装载表会漂移，
#: 漂移的那一天就会出现"装载了但没进清单"的静默缺口。
AV_MANIFEST_TOOL_FILES: Tuple[str, ...] = tuple(_deps().ENTRY_FILES)
#: 一并纳入身份的冻结合同（目标合同改口径即身份变化）。
AV_MANIFEST_CONTRACT_FILES: Tuple[str, ...] = (
    "contracts/group-dev-v1.json", "contracts/action-value-v1.json",
)
#: 基线（V2 固定对照）实现模块：改动基线即身份变化。
AV_MANIFEST_BASELINE_MODULES: Tuple[str, ...] = (
    "hangma_bot.policy.heuristic_v2", "hangma_bot.policy.evaluation_v2",
    "hangma_bot.policy.weights", "hangma_bot.policy.white_discard_guard",
    "hangma_bot.policy.heuristic_v1",
)
#: 统计器版本（口径变化必须换版本串，进身份）。
AV_MANIFEST_STATISTICS_VERSION = "sitin-paired-stage-stats/1"


def av_dependency_file_reader(path: Path) -> bytes:
    """依赖内容读取的**单一入口**（默认读实际文件字节）。

    S2：冻结清单的一切文件面都经本入口读取——测试/演练可注入以模拟"某依赖已被
    改动"（方法体、数学后端、面板、合同），无需真的改源码。
    """

    return Path(path).read_bytes()


def _av_file_digest(path: Path) -> str:
    """一个依赖文件的内容摘要（经 av_dependency_file_reader）。"""

    return hashlib.sha256(av_dependency_file_reader(Path(path))).hexdigest()


def _av_module_origin(dotted: str) -> Optional[Path]:
    """模块名 → 实际文件路径（不可导入返回 None，不伪造）。"""

    import importlib.util

    try:
        spec = importlib.util.find_spec(dotted)
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return None
    origin = getattr(spec, "origin", None)
    return Path(origin) if origin else None


def _av_module_imports(path: Path, dotted: str) -> List[str]:
    """解析一个第一方模块的 import（含函数内与相对导入）→ 绝对模块名列表。

    S2/P3：实现已统一到 `sitin_deps.module_imports`（单一来源）。旧实现在**包**的
    `__init__.py` 上按父包解析相对导入，`hangma_bot/offline/__init__.py` 的
    `from .evaluate import ...` 被算成 `hangma_bot.evaluate`（不存在），而真实依赖
    `hangma_bot.offline.evaluate` 因此没进闭包——这正是 S2 漏项的一个来源。
    """

    refs = _deps().module_imports(Path(path), dotted)
    names: List[str] = []
    for ref in refs:
        if ref.required:
            names.append(ref.name)
            continue
        # `from X import y` 里的 y：只有当它**确实是一个模块**时才是依赖
        # （例如 `from hangma_bot import bootstrap` ⇒ hangma_bot.bootstrap）；
        # 普通属性名（常量/类/函数）不是模块，不记。判定按文件存在性，不猜。
        if _av_module_origin(ref.name) is not None:
            names.append(ref.name)
    return names


def av_dependency_closure(roots: Sequence[str]) -> Tuple[Dict[str, str], List[str]]:
    """第一方传递依赖闭包：模块名 → 文件内容摘要；不可解析的模块另记 missing。

    S2：复审指出"部分文件内容摘要未覆盖 hand_analysis/_standard 等规则传递依赖"
    ——本函数按实际 import 图走闭包（含函数内导入与相对导入），因此规则来源、
    数学后端（含 .so 原生后端，按字节哈希）、投影与执行器都在身份内。
    """

    digests: Dict[str, str] = {}
    missing: List[str] = []
    queue: List[str] = list(roots)
    while queue:
        dotted = queue.pop(0)
        if dotted in digests or dotted in missing:
            continue
        origin = _av_module_origin(dotted)
        if origin is None or not origin.is_file():
            missing.append(dotted)
            continue
        try:
            digests[dotted] = hashlib.sha256(
                av_dependency_file_reader(origin)).hexdigest()
        except OSError:
            missing.append(dotted)
            continue
        for child in _av_module_imports(origin, dotted):
            if child.startswith("hangma_bot.") and child not in digests:
                queue.append(child)
    return digests, sorted(missing)


def av_entry_call_graph(*, entries: Optional[Sequence[str]] = None,
                         ) -> Dict[str, Any]:
    """**入口调用图**：真实装配入口 → 第一方模块 / 同目录工具模块的传递闭包（S2/P3）。

    为什么不能只哈希工具文件自身：`sitin_natural_panel.py` 是自然面板的**真实装配
    入口**（第 71 行导入、第 452 行调用 `offline.evaluate.drive_match`），
    `drive_match` 又经组合根 `bootstrap.build_evaluation_runtime` 装配
    `SimulationEngine`。只哈希工具文件字节，等于宣称"改驱动方法体不影响身份"——
    复审实测的反例正是如此（纯内存改 `drive_match` 方法体、只编译不执行，摘要不变、
    身份核验照样通过）。

    实现委托 `sitin_deps.entry_call_graph`（登记表模块，单一来源），文件读取仍走
    `av_dependency_file_reader` 这一**唯一读取入口**，因此测试/演练可以用注入的
    reader 模拟"某个依赖已被改动"，无需真的改源码。
    """

    return _deps().entry_call_graph(reader=av_dependency_file_reader,
                                    tools_dir=TOOLS_DIR,
                                    src_root=_project_file(_PROJECT_ROOT, REPO_ROOT / "src"),
                                    entries=entries)


def av_entry_coverage_gaps(*, graph: Optional[Mapping[str, Any]] = None,
                           covered: Optional[Iterable[str]] = None,
                           ) -> List[Dict[str, Any]]:
    """入口覆盖缺口（空列表=可出清单）：未登记的动态装载 + 解析不到的第一方模块。

    S2/P3 修复项 2：动态 sibling 装载必须显式登记，**登记不到即失败关闭**。
    缺口在这里是"硬失败"（`av_frozen_manifest` 直接抛 `ManifestCoverageGap`），
    不是警告——警告会被忽略，而漏项的后果是旧结果跨实现复用（R8 §3 S2）。

    graph：可传入已算好的 av_entry_call_graph（避免同一入口图算两遍）；
    covered：已登记的第一方模块集合（传入后额外核对"按名装载"的模块是否都已登记，
    见 sitin_deps.scan_literal_module_loads）。
    """

    return _deps().coverage_gaps(reader=av_dependency_file_reader,
                                 tools_dir=TOOLS_DIR,
                                 src_root=_project_file(_PROJECT_ROOT, REPO_ROOT / "src"),
                                 graph=graph, covered=covered)


def av_analysis_config() -> Dict[str, Any]:
    """实际分析配置（ValueAnalysisLimits 的**实际值**，不是代码内字面量）。"""

    interface = av_gates()._av_module("hangma_bot.hangma.interface")
    limits = interface.ValueAnalysisLimits()
    return {"value_analysis_limits": {
        "max_expansions": int(limits.max_expansions),
        "max_routes_per_candidate": int(limits.max_routes_per_candidate)}}


def av_root_purpose_identity(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """根用途面：本次运行的算子/情景/面板种子/前缀路由/自然根与座位/生成模式。"""

    plan = plan or {}
    return {
        "operator": plan.get("operator"), "predicate": plan.get("predicate"),
        "opponent": plan.get("opponent"), "panel_seed": plan.get("panel_seed"),
        "prefix_source": plan.get("prefix_source"),
        "natural_roots": plan.get("natural_roots"),
        "natural_seats": plan.get("natural_seats"),
        "natural_opponents": list(plan.get("natural_opponents") or ("H", "M")),
        "generation_mode": plan.get("generation_mode"),
        "seed_name": plan.get("seed_name"),
    }


# ===========================================================================
# P7 · 家族通道接线声明（计划里的通道配置必须进身份）
# ===========================================================================


def _av_plan_json_value(value: Any) -> Any:
    """计划里的任意值 → 可稳定序列化的 JSON 值（认不出的类型显式标出，不猜内容）。

    冻结摘要建立在 `canonical_json`（json.dumps）上：**不可序列化的值会让整份清单
    算不出来**。计划来自 JSON，正常路径不会走到兜底分支；这里只让"有人塞了非 JSON
    对象"变成**可核对的身份内容**（类型名进摘要），而不是崩在摘要计算里。
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _av_plan_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_av_plan_json_value(item) for item in value]
    return {"unrepresentable_type": type(value).__name__}


def _av_plan_family_channel(plan: Mapping[str, Any]) -> Optional[str]:
    """计划里声明的家族通道（缺省 None = 不接线；与 av_start_iteration 同一判据）。"""

    declared = (plan or {}).get("family_channel")
    if declared in (None, ""):
        return None
    return str(declared)


def av_family_channel_identity(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """家族通道面（P7）：本次启用的是**哪个**家族——声明值 + 解析出的族名 + 登记表。

    为什么必须进身份（R9 §14.3 机器实测）：同一计划下 family_channel 有/无，冻结清单
    摘要曾**逐字相同** ⇒ 两次只差家族接线配置的运行拿到同一身份、旧结果被跨配置复用
    （"未解释身份冲突"）。关口二第 1 步明确要启用一个家族通道，因此身份必须覆盖它。

    **不是布尔位**：这里落声明原文与解析出的族名（family_channel_of 的**唯一映射点**
    在 sitin_archive），并列出登记表里的全部家族，供事后核对"启用的是哪一个"。逐条
    刷新声明在 `av_family_refresh_identity`（family_refresh 面）。
    """

    declared = _av_plan_family_channel(plan)
    family: Optional[str] = None
    problems: List[Dict[str, Any]] = []
    if declared is not None:
        try:
            family = av_archive().family_channel_of(declared)
        except Exception as error:                      # noqa: BLE001（见下）
            # 解析异常不静默：异常类型与声明原文一并进身份（身份算不出来比身份漏项
            # 更糟，所以这里只登记、不抛出）。
            problems.append({"declaration": declared,
                             "reason": "通道解析异常：{0}".format(
                                 type(error).__name__)})
        if family is None and not problems:
            problems.append({"declaration": declared, "reason": (
                "声明的通道不是已登记家族（sitin_archive.FAMILIES）：家族评价不会"
                "接线，但配置仍按原文进身份")})
    scope = av_family_scope(family) if family is not None else av_family_scope(None)
    if declared is not None and family is not None and scope["status"] != "enabled":
        # S4：声明了本版未启用的族 → 身份里显式记下"跳过 + 原因"，不让"零家族评价"
        # 与"跑过但没样本"混为一谈（换启用集合也必然改变本面摘要）。
        problems.append({"declaration": declared, "reason": (
            "声明的家族 {0} 在本版状态为 {1}：调度显式跳过（{2}）").format(
                family, scope["status"], scope["reason"])})
    return {
        "enabled": declared is not None,
        "declared": declared,
        "family": family,
        "families": sorted(str(item) for item in av_archive().FAMILIES),
        # S4：**启用家族集合**是身份的一部分（只启用 branch；其余显式 inactive）。
        "enabled_families": list(AV_FAMILY_ENABLED_FAMILIES),
        "inactive_families": list(AV_FAMILY_INACTIVE_FAMILIES),
        "scope": {"status": scope["status"], "reason": scope["reason"],
                  "stop_reason": scope["stop_reason"]},
        "problems": problems,
        "note": ("家族通道**按开轮显式声明启用**（plan.family_channel）：缺省 = 不接线、"
                 "零家族评价、零行为变化；启用时身份必须能区分「哪个族」与"
                 "**本版启用集合**（S4：仅 branch，其余显式 inactive 并由调度跳过），"
                 "故本面落声明原文、解析族名与范围状态"),
    }


def av_family_refresh_identity(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """刷新声明面（P7）：plan.family_refresh **逐条内容**（不是布尔位、不是条数）。

    声明批是家族评价内容的输入：同一声明下换面板种子 / 换根序号 / 改座位数 / 增删
    一条，补根评价跑的就是另一批根。因此逐条落：
      - 声明原文（键值原样规范化，未知键也进身份——新增通道参数不会静默漏项）；
      - **派生根身份**（生成器 × 子场景 × 情景 × 种子 × 序号 → root_id / 执行种子），
        与调度侧 `av_family_root_descriptor` 同一实现，不留"改了根只变台账不变身份"；
      - 调用方声明的顺序（列表顺序即调度顺序，顺序变化同样进身份）。
    """

    raw = (plan or {}).get("family_refresh") or ()
    rows: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    for position, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            rows.append({"position": position, "declaration": _av_plan_json_value(entry),
                         "reason": "声明不是映射：原样进身份，不忽略"})
            problems.append({"position": position,
                             "reason": "声明不是映射（不猜、不忽略）"})
            continue
        row: Dict[str, Any] = {str(key): _av_plan_json_value(value)
                               for key, value in entry.items()}
        row["resolved_root"] = _av_declared_root_view(plan, entry)
        if "error" in row["resolved_root"]:
            problems.append({"position": position,
                             "reason": "声明派生不出根身份：{0}".format(
                                 row["resolved_root"]["error"])})
        rows.append(row)
    return {
        "count": len(rows),
        "declarations": rows,
        "problems": problems,
        "note": ("开轮声明的家族刷新批（显式根声明：子场景 × 对手情景 × 面板种子 × "
                 "根序号 × 座位数）；逐条原文与派生根身份进摘要"),
    }


def _av_declared_root_view(plan: Mapping[str, Any],
                           entry: Mapping[str, Any]) -> Dict[str, Any]:
    """一条刷新声明 → 派生根身份；派生失败即**原样记错**（不抛出、不猜）。"""

    try:
        descriptor = av_family_root_descriptor(
            prefix_source=str((plan or {}).get("prefix_source")
                              or "scripted_fixture"),
            sub_scenario=str(entry.get("sub_scenario") or ""),
            opponent_mix=str(entry.get("opponent_mix") or ""),
            panel_seed=entry.get("panel_seed"),
            root_index=entry.get("root_index"))
    except (TypeError, ValueError, KeyError) as error:
        return {"error": str(error)[:200]}
    return {"root_id": str(descriptor["root_id"]),
            "root_seed": int(descriptor["root_seed"]),
            "generator": str(descriptor["generator"]),
            "root_identity_schema": str(descriptor.get("root_identity_schema") or ""),
            "seed_derivation": str(descriptor.get("seed_derivation") or "")}


def _av_digest_mapping(mapping: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(dict(mapping)))


def av_development_behavior_panel(declaration: Any) -> Optional[Dict[str, Any]]:
    """核验显式声明的真实开发面板及全部窗口；内容漂移立即拒绝，不静默换面板。"""
    if declaration is None:
        return None
    if not isinstance(declaration, Mapping) or set(declaration) != {"path", "panel_digest"}:
        raise ValueError("development_behavior_panel 必须声明 path 和 panel_digest")
    path = Path(declaration["path"]).resolve()
    panel_digest, windows = _sibling("sitin_real_behavior").load_panel(path)
    if panel_digest != declaration["panel_digest"]:
        raise ValueError("真实开发行为面板摘要漂移，拒绝推进")
    return {"path": str(path), "panel_digest": panel_digest}


def av_frozen_manifest(*, plan: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """重算本次运行的**冻结清单**（S2：每个推进/恢复入口自行调用）。

    十三个面：规则（含 hand_analysis/_standard 等传递依赖）/ 投影 / 执行器 /
    模拟器 / 统计器 / 基线 / 对手（含目标合同）/ 分析配置 / 面板 / 根用途 /
    **入口调用图** / **家族通道** / **家族刷新声明**。候选面不在此清单内（它在生成步才定），由 av_verify_run_identity
    用入口重算的 candidate_id 单独核验——避免"开轮时没有候选"与"恢复时有候选"互相矛盾。

    入口调用图面（S2/P3）：从 `sitin_deps.ENTRY_FILES`（编排状态机 + 桌赛执行件 +
    全部已登记 sibling + 登记表自身）出发，走 `hangma_bot.*` 模块与同目录工具模块的
    传递闭包，因此桌赛驱动（`hangma_bot.offline.evaluate`）与组合根
    （`hangma_bot.bootstrap`）及其传递依赖都在摘要内。

    家族通道面（S2/P7）：入口调用图覆盖的是**代码**，家族接线配置在**计划**里——
    `plan.family_channel` / `plan.family_refresh` 声明了本次启用哪个族、补根评价跑
    哪些根，直接影响评价内容。它们此前不进任何面，于是"只差家族配置的两次运行"拿到
    同一身份（R9 §14.3 机器实测：摘要逐字相同）。

    **缺项即失败关闭**：入口里出现未登记的动态装载、或第一方模块解析不到文件时，
    直接抛 `sitin_deps.ManifestCoverageGap`（不是记一条 warning 继续）——
    一份"看起来完整"的清单比没有清单更危险。
    """

    gates = av_gates()
    executor = gates._av_module("hangma_bot.policy.action_value_executor")
    roots = list(executor.FIRST_PARTY_DIGEST_MODULES) + list(AV_MANIFEST_ROOT_MODULES)
    closure, missing = av_dependency_closure(roots)
    # N4：基线（V2 固定对照）与对手/驱动同样走**真实传递依赖**——此前只哈希
    # AV_MANIFEST_BASELINE_MODULES 里模块自身，于是 heuristic_v1/evaluation_v2
    # 真正 import 的 evaluation_v1 / weights_v1 / kernel.actions 不在任何摘要面内。
    baseline_closure, baseline_missing = av_dependency_closure(
        AV_MANIFEST_BASELINE_MODULES)
    tools = {name: _av_file_digest(_project_file(_PROJECT_ROOT, TOOLS_DIR / name))
             for name in AV_MANIFEST_TOOL_FILES}
    contracts = {
        name: _av_file_digest(_project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
                              / name))
        for name in AV_MANIFEST_CONTRACT_FILES}
    baseline: Dict[str, Optional[str]] = {}
    for name in AV_MANIFEST_BASELINE_MODULES:
        origin = _av_module_origin(name)
        baseline[name] = (_av_file_digest(origin) if origin is not None else None)
    rules = {name: digest for name, digest in closure.items()
             if name.startswith("hangma_bot.hangma.")}
    projection = {name: digest for name, digest in closure.items()
                  if name in ("hangma_bot.policy.action_value",
                              "hangma_bot.policy.action_value_policy",
                              "hangma_bot.policy.action_value_seeds")}
    simulator = {name: digest for name, digest in closure.items()
                 if name.startswith("hangma_bot.simulation.")}
    # —— S2/P3：入口调用图（真实装配入口 → 桌赛驱动 / 组合根 / 工具模块）。
    #    覆盖缺口与调用图共用同一次计算：缺一项就必须失败关闭，而不是"图算出来了、
    #    缺口记成警告"——一份看起来完整的清单比没有清单更危险。
    entry_graph = av_entry_call_graph()
    entry_nodes = entry_graph["nodes"]
    entry_module_closure = {
        str(node["name"]): str(node["sha256"])
        for key, node in entry_nodes.items() if node.get("kind") == "module"}
    entry_tool_closure = {
        str(node["name"]) + ".py": str(node["sha256"])
        for key, node in entry_nodes.items() if node.get("kind") == "tool"}
    coverage_gaps = av_entry_coverage_gaps(
        graph=entry_graph,
        covered=(set(closure) | set(baseline_closure)
                 | set(entry_module_closure)))
    if coverage_gaps:
        raise _deps().ManifestCoverageGap(
            "冻结清单覆盖缺口，拒绝出清单：{0}".format(canonical_json(coverage_gaps)))
    natural = _sibling("sitin_natural_panel")
    opportunities = _sibling("sitin_opportunities")
    entry_files = {
        str(node["name"]) + ".py": str(node["sha256"])
        for key, node in sorted(entry_nodes.items())
        if node.get("kind") == "tool" and key in set(entry_graph["entries"])}
    entry_edges = {key: list(value) for key, value in entry_graph["edges"].items()}
    surfaces = {
        "rules": {"digest": _av_digest_mapping(rules), "modules": rules,
                  "note": ("第一方传递依赖闭包中的规则来源"
                           "（含 hand_analysis/_standard 与原生数学后端）")},
        "projection": {"digest": _av_digest_mapping(projection),
                       "modules": projection},
        "executor": {"version": str(executor.EXECUTOR_VERSION),
                     "modules": {name: digest for name, digest in closure.items()
                                 if name == "hangma_bot.policy.action_value_executor"}},
        "simulator": {"digest": _av_digest_mapping(simulator),
                      "modules": simulator},
        "statistics": {"version": AV_MANIFEST_STATISTICS_VERSION,
                       "modules": {name: tools[name]
                                   for name in ("sitin_archive.py",
                                                "sitin_stage.py")}},
        "baseline": {"baseline_id": AV_BASELINE_ID, "modules": baseline_closure,
                     "roots": list(AV_MANIFEST_BASELINE_MODULES),
                     "missing": list(baseline_missing),
                     "entry_digests": baseline},
        "opponent": {"scenario": (plan or {}).get("opponent"),
                     "contracts": contracts,
                     "contract_sha256": contracts.get(
                         "contracts/group-dev-v1.json")},
        "analysis_config": dict(
            av_analysis_config(),
            module_sha256={name: digest for name, digest in closure.items()
                           if name == "hangma_bot.hangma.interface"}),
        "panel": {"generators": {
                      "natural": getattr(natural, "NATURAL_PANEL_GENERATOR", None),
                      "conditional": getattr(
                          opportunities, "GENERATOR_SCRIPTED_FIXTURE", None),
                      "stage_account_mode": getattr(natural, "STAGE_ACCOUNT_MODE",
                                                    None)},
                  # P9b（面级表述修正）：八谓词的冻结合同实现也属"面板"面——它此前只经
                  # entry_tool_closure 段进摘要、不隶属任何面，而清单里名为 projection 的
                  # 面其实是 action-value 策略侧；改阈值/改三值语义却不改面级表述会误导
                  # 后来人（"身份覆盖完整、表述不完整"）。此处显式挂上。
                  # 摘要口径：登记过的同目录工具取 tool_files 面；谓词模块未登记在
                  # AV_MANIFEST_TOOL_FILES（由 sitin_deps.ENTRY_FILES 派生，本包不改它），
                  # 按同一读入口 _av_file_digest 直接取字节摘要——两者同源、不会漂移。
                  "modules": {name: (tools.get(name)
                                     or _av_file_digest(_project_file(_PROJECT_ROOT, TOOLS_DIR / name)))
                              for name in ("sitin_natural_panel.py",
                                           "sitin_opportunities.py",
                                           "sitin_predicates_v4.py")}},
        "root_purpose": av_root_purpose_identity(plan or {}),
        "development_behavior_panel": av_development_behavior_panel(
            (plan or {}).get("development_behavior_panel")),
        "supervisor_feedback": (plan or {}).get("supervisor_feedback"),
        "author_feedback_mode": av_feedback().author_feedback_mode(
            (plan or {}).get("author_feedback_mode")),
        # —— P7：家族通道接线声明（声明内容进身份，不是布尔位）——
        "family_channel": av_family_channel_identity(plan or {}),
        "family_refresh": av_family_refresh_identity(plan or {}),
        "entry_graph": {
            "entries": sorted(entry_files),
            "nodes": len(entry_nodes),
            "module_nodes": len(entry_module_closure),
            "tool_nodes": len(entry_tool_closure),
            "missing": list(entry_graph["missing"]),
            # 走到这里必然为空：非空时上面已抛 ManifestCoverageGap（缺项失败关闭）。
            "coverage_gaps": list(coverage_gaps),
            "note": ("真实装配入口（编排状态机 + 桌赛执行件 + 已登记 sibling）"
                     "→ 第一方模块 / 同目录工具模块的传递闭包；"
                     "桌赛驱动与组合根在内，见 entry_edges"),
        },
    }
    return {"schema": AV_FROZEN_MANIFEST_SCHEMA, "surfaces": surfaces,
            "module_closure": closure, "missing_modules": missing,
            "baseline_module_closure": baseline_closure,
            "baseline_missing_modules": baseline_missing,
            "tool_files": tools, "contract_files": contracts,
            "roots": sorted(set(roots)),
            "entry_files": entry_files,
            "entry_module_closure": entry_module_closure,
            "entry_tool_closure": entry_tool_closure,
            "entry_edges": entry_edges,
            "entry_missing": list(entry_graph["missing"]),
            "entry_coverage_gaps": list(coverage_gaps)}


def _av_sorted_mapping(mapping: Any) -> Dict[str, Any]:
    """规范化映射：键排序、值原样（摘要的稳定性由它保证）。"""

    return {str(key): mapping[key] for key in sorted(mapping or {})}


def av_manifest_identity_payload(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """摘要真正吃的**完整规范化依赖清单**（N4）。

    为什么不能再只吃 surfaces：sitin_search.py、kernel/actions.py 只出现在顶层
    tool_files / module_closure 里，于是"清单明细看得到、摘要却不变"——恢复身份
    形同虚设。这里把面、传递闭包明细、基线传递闭包、工具/合同文件、缺失模块与
    根集合全部规范化后一起入摘要：清单里登记了什么，摘要就绑定什么。
    """

    return {
        "schema": manifest.get("schema"),
        "roots": sorted(str(item) for item in (manifest.get("roots") or ())),
        "surfaces": dict(manifest.get("surfaces") or {}),
        "module_closure": _av_sorted_mapping(manifest.get("module_closure")),
        "baseline_module_closure": _av_sorted_mapping(
            manifest.get("baseline_module_closure")),
        "tool_files": _av_sorted_mapping(manifest.get("tool_files")),
        "contract_files": _av_sorted_mapping(manifest.get("contract_files")),
        "missing_modules": sorted(str(item)
                                  for item in (manifest.get("missing_modules") or ())),
        "baseline_missing_modules": sorted(
            str(item) for item in (manifest.get("baseline_missing_modules") or ())),
        #: S2/P3 入口调用图（真实装配入口 → 桌赛驱动 / 组合根 / 工具模块）：
        #: 「清单明细里看得到、摘要却不变」的假身份在这里被堵死——入口文件的字节、
        #: 它真正 walk 到的每个第一方模块与工具模块、以及图的边都进摘要。
        "entry_files": _av_sorted_mapping(manifest.get("entry_files")),
        "entry_module_closure": _av_sorted_mapping(
            manifest.get("entry_module_closure")),
        "entry_tool_closure": _av_sorted_mapping(
            manifest.get("entry_tool_closure")),
        "entry_edges": _av_sorted_mapping(manifest.get("entry_edges")),
        "entry_missing": sorted(str(item)
                                for item in (manifest.get("entry_missing") or ())),
        "entry_coverage_gaps": list(manifest.get("entry_coverage_gaps") or ()),
    }


def av_frozen_manifest_digest(manifest: Mapping[str, Any]) -> str:
    """冻结清单摘要（N4：吃完整规范化依赖清单，不再只吃 surfaces）。"""

    return sha256_text(canonical_json(
        av_manifest_identity_payload(manifest)))


def av_changed_manifest_surfaces(stored: Mapping[str, Any],
                                 recomputed: Mapping[str, Any]) -> List[str]:
    """逐面/逐段定位变化（报告用；空列表表示十三个面与全部全局段都相同）。"""

    stored_payload = av_manifest_identity_payload(stored)
    fresh_payload = av_manifest_identity_payload(recomputed)

    def _section(payload: Mapping[str, Any], name: str) -> Any:
        if name in AV_FROZEN_MANIFEST_SURFACES:
            return (payload.get("surfaces") or {}).get(name)
        return payload.get(name)

    changed = [name for name in AV_FROZEN_MANIFEST_SECTIONS
               if canonical_json(_section(stored_payload, name))
               != canonical_json(_section(fresh_payload, name))]
    extra = sorted(set(stored_payload) ^ set(fresh_payload))
    return changed + [name for name in extra if name not in changed]


def av_identity_expectation_view(state: Mapping[str, Any],
                                 manifest: Mapping[str, Any],
                                 *, candidate_source: Optional[str] = None,
                                 ) -> Dict[str, Any]:
    """调用方 identity 的**额外期望**可核对面：全部来自入口重算值。

    只有档案步产生的 panel_epoch / evaluation_id 不是入口可重算量（与在案值比对）；
    候选身份用入口重算的 candidate_id 覆盖在案值，因此"旧摘要 + 空 identity"不再
    是可用的绕过材料。
    """

    gates = av_gates()
    plan = dict(state.get("plan") or {})
    surfaces = dict(manifest.get("surfaces") or {})
    identity = dict(state.get("identity") or {})
    view: Dict[str, Any] = {
        "run_id": state.get("run_id"),
        "frozen_manifest_digest": av_frozen_manifest_digest(manifest),
        "contract_sha256": gates.av_contract()[1],
        "target_contract_sha256": (surfaces.get("opponent") or {}).get(
            "contract_sha256"),
        "executor_version": (surfaces.get("executor") or {}).get("version"),
        "deps_digest": gates.av_deps_digest(),
        "value_analysis_limits": (surfaces.get("analysis_config") or {}).get(
            "value_analysis_limits"),
        "operator": plan.get("operator"), "predicate": plan.get("predicate"),
        "opponent": plan.get("opponent"), "panel_seed": plan.get("panel_seed"),
        "generation_mode": plan.get("generation_mode"),
        "panel_epoch": identity.get("panel_epoch"),
        "evaluation_id": identity.get("evaluation_id"),
    }
    source = candidate_source
    if source is None:
        source = state.get("candidate_source")
    if source:
        view["candidate_id"] = gates.av_identity_binding(source)["candidate_id"]
    elif identity.get("candidate_id"):
        view["candidate_id"] = identity.get("candidate_id")
    return view


def av_verify_run_identity(state: Mapping[str, Any], *,
                           candidate_source: Optional[str] = None,
                           expected: Optional[Mapping[str, Any]] = None,
                           entry: str = "advance",
                           ) -> Tuple[bool, str, Dict[str, Any]]:
    """恢复身份核验（S2）：**入口自算冻结清单**，调用方 identity 只作额外期望。

    规则（任一条不满足即拒绝，拒绝发生在任何新费用/新结果写入之前）：
    1. 在案状态必须带开轮冻结的清单与摘要（旧版本状态拒绝恢复）；
    2. 入口重算清单，逐面比对——任何一面（规则/投影/执行器/模拟器/统计器/基线/
       对手/分析配置/面板/根用途/**入口调用图**/**家族通道**/**家族刷新声明**）
       变化即拒绝续写旧结果；P7 起家族接线配置（开关与刷新声明内容）也在其中：
       S2/P3：清单覆盖出现缺口（未登记的动态装载 / 第一方模块解析不到）同样拒绝恢复，
       缺口不降级为警告；
    3. 候选身份由入口重算（gates.av_identity_binding）与在案 candidate_id 比对；
    4. expected 里每个字段与**入口重算值**比对（不是与在案值比对，也不是唯一依据）
       ——空 expected / None 不影响结论，因为 1—3 已独立成立。
    """

    identity = dict(state.get("identity") or {})
    stored = identity.get("frozen_manifest")
    stored_digest = identity.get("frozen_manifest_digest")
    if not isinstance(stored, Mapping) or not stored_digest:
        return False, (
            "在案状态缺开轮冻结清单（frozen_manifest/frozen_manifest_digest）："
            "旧版本状态不可恢复，须按新身份重开评价（S2）"), {}
    try:
        manifest = av_frozen_manifest(plan=state.get("plan"))
    except _deps().ManifestCoverageGap as error:
        # 覆盖缺口是**拒绝恢复**的理由，不是崩溃：缺一项就可能有一份实现没进清单，
        # 此时任何"继续"都在拿旧结果赌新实现（S2/P3 修复项 2）。
        return False, (
            "身份核验失败（{0}）：冻结清单存在覆盖缺口 → 拒绝恢复"
            "（不续写旧结果、不产生新费用）：{1}").format(entry, error), {}
    except (ValueError, OSError, TypeError, KeyError) as error:
        return False, "身份核验失败（{0}）：冻结输入不可读取或已漂移：{1}".format(entry, error), {}
    fresh_digest = av_frozen_manifest_digest(manifest)
    if str(fresh_digest) != str(stored_digest):
        changed = av_changed_manifest_surfaces(stored, manifest)
        return False, (
            "身份变更（{0}）：面 {1} 与开轮冻结清单不一致 → 拒绝恢复"
            "（不续写旧结果、不产生新费用；身份变更须开新评价）".format(
                entry, "、".join(changed) or "全局摘要")), manifest
    source = candidate_source
    if source is None:
        source = state.get("candidate_source")
    if source and identity.get("candidate_id"):
        recomputed_id = av_gates().av_identity_binding(source)["candidate_id"]
        if str(recomputed_id) != str(identity.get("candidate_id")):
            return False, (
                "身份变更（{0}）：候选面不符（在案 candidate_id {1}，入口重算 {2}）"
                "→ 拒绝恢复").format(entry, str(identity.get("candidate_id"))[:16],
                                     str(recomputed_id)[:16]), manifest
    if expected:
        if not isinstance(expected, Mapping):
            return False, "identity 必须是映射（得到 {0}）".format(
                type(expected).__name__), manifest
        view = av_identity_expectation_view(state, manifest,
                                            candidate_source=candidate_source)
        for key, value in expected.items():
            if key not in view:
                return False, (
                    "期望字段 {0} 不是入口可核验身份面（S2：只接受可重算字段，"
                    "不接受任意字符串比对）").format(key), manifest
            if str(view.get(key)) != str(value):
                return False, (
                    "身份变更（{0}）：期望字段 {1} 与入口重算值不符（期望 {2}，"
                    "入口实际 {3}）→ 拒绝恢复").format(
                        entry, key, str(value)[:16], str(view.get(key))[:16]), manifest
    return True, "", manifest


# ===========================================================================
# S3 · 实例任务台账、检查点与恢复对账
# ===========================================================================

#: 实例任务台账 schema（**完整评价身份**为唯一键；attempts 为不可替换的尝试历史）。
#: A3：/2 起键含候选、对手情景、面板种子/根序号（旧键把这些维度省掉，导致同运行目录
#: 内两次候选评价、或同候选的 H/M 撞键互吞）。
AV_INSTANCE_SCHEMA = "sitin-av-instance-tasks/2"
#: 检查点 schema（每一步的"已开始/已完成/费用/不可变结果摘要"）。
AV_CHECKPOINT_SCHEMA = "sitin-av-checkpoint/1"
#: 生成步检查点名（S3：回复已存在但生成状态未提交的恢复对账面）。
AV_GENERATION_CHECKPOINT = "generation"

#: 完整评价身份（A3）：候选 × 对手情景 × 面板种子（随机映射）× 根（内容身份） ×
#: 座位 × 臂 × 赛程。缺任何一维都会让两个真实实例共用一个键，后者的记录把前者顶掉。
AV_INSTANCE_IDENTITY_FIELDS: Tuple[str, ...] = (
    "candidate_id", "opponent_mix", "panel_seed", "source_root_id", "root_index",
    "root_seed", "seat", "arm", "schedule",
)
#: 台账行的身份字段：同一键上这些字段只能逐字一致；不一致即身份冲突（不是路径差异）。
AV_INSTANCE_ROW_IDENTITY_FIELDS: Tuple[str, ...] = AV_INSTANCE_IDENTITY_FIELDS + (
    "participant_id", "cache_key", "evaluation_scope",
)
#: 尝试的终态：进入后不得回退为 started，也不得在同一 attempt_no 上二次覆写。
AV_INSTANCE_TERMINAL_STATUSES: Tuple[str, ...] = ("completed", "aborted")
#: 臂：候选臂是本候选的**评价**；基线臂是全体候选共享的固定 V2 对照**缓存**。
AV_INSTANCE_ARMS: Tuple[str, ...] = ("baseline", "candidate")
#: 两种评价范围：候选评价 / 候选与基线共享缓存（A3 要求显式可分）。
AV_INSTANCE_SCOPE_CANDIDATE = "candidate_evaluation"
AV_INSTANCE_SCOPE_SHARED_BASELINE = "shared_baseline_cache"


def _av_instance_part(name: str, value: Any) -> str:
    return "{0}={1}".format(name, "" if value is None else str(value))


def av_instance_identity_key(*, candidate_id: Any, opponent_mix: Any,
                             panel_seed: Any, source_root_id: Any, seat: Any,
                             arm: Any, schedule: Any, root_index: Any = None,
                             root_seed: Any = None) -> str:
    """完整评价身份 → 实例键（A3 唯一键）。

    每一维都带字段前缀，因此键是**可读且可分组**的（排查时不必反解哈希）。根内容与
    随机映射由（对手情景、面板种子、根序号、根种子、来源根标识）共同锁定——家族根的
    文本身份自身不含情景与种子（见 av_family_root_id），必须在键里补上，否则同候选
    同子场景同索引的 H 与 M 会共用一条实例记录。
    """

    return "|".join((
        _av_instance_part("cand", candidate_id),
        _av_instance_part("mix", opponent_mix),
        _av_instance_part("seed", int(panel_seed)),
        _av_instance_part("root", source_root_id),
        _av_instance_part("rootidx", root_index),
        _av_instance_part("rootseed", root_seed),
        _av_instance_part("seat", int(seat)),
        _av_instance_part("arm", arm),
        _av_instance_part("sched", schedule),
    ))


def av_instance_row(*, candidate_id: Any, opponent_mix: Any, panel_seed: Any,
                    source_root_id: Any, seat: Any, arm: Any, schedule: Any,
                    root_index: Any = None, root_seed: Any = None,
                    participant_id: Any = None, planned_tables: Any = None
                    ) -> Dict[str, Any]:
    """一个实例任务行（完整身份 + 两种评价范围的显式标记）。

    `evaluation_scope` 把「候选评价」与「候选与基线共享缓存」分开：
      - 候选臂：本候选自己的评价，键 = 完整身份（含候选）；
      - 基线臂：固定 V2 对照，**跨候选共用同一份缓存身份**（cache_key 不含候选），
        但仍是本候选这一轮真实跑过的实例（instance_key 含候选，不与他人记录互吞）。
    行在真实副作用**之前**即可确定性算出，因此"已开始"能在跑桌赛前落盘。
    """

    if str(arm) not in AV_INSTANCE_ARMS:
        raise ValueError("未知臂 {0!r}（应为 {1}）".format(arm, list(AV_INSTANCE_ARMS)))
    key = av_instance_identity_key(
        candidate_id=candidate_id, opponent_mix=opponent_mix, panel_seed=panel_seed,
        source_root_id=source_root_id, seat=seat, arm=arm, schedule=schedule,
        root_index=root_index, root_seed=root_seed)
    shared = str(arm) == "baseline"
    cache_key = av_instance_identity_key(
        candidate_id=AV_BASELINE_ID, opponent_mix=opponent_mix,
        panel_seed=panel_seed, source_root_id=source_root_id, seat=seat, arm=arm,
        schedule=schedule, root_index=root_index, root_seed=root_seed) if shared else key
    row: Dict[str, Any] = {
        "instance_key": key, "cache_key": cache_key,
        "evaluation_scope": (AV_INSTANCE_SCOPE_SHARED_BASELINE if shared
                             else AV_INSTANCE_SCOPE_CANDIDATE),
        "candidate_id": str(candidate_id), "opponent_mix": str(opponent_mix),
        "panel_seed": int(panel_seed), "source_root_id": str(source_root_id),
        "root_index": (None if root_index is None else int(root_index)),
        "root_seed": (None if root_seed is None else int(root_seed)),
        "seat": int(seat), "arm": str(arm), "schedule": str(schedule),
    }
    if participant_id is not None:
        row["participant_id"] = participant_id
    if planned_tables is not None:
        row["planned_tables"] = planned_tables
    return row


def av_instance_key(*, source_root_id: Any, seat: Any, arm: Any,
                    schedule: Any, identity: Any = None) -> str:
    """**旧形态**实例键：来源根 × 座位 × 臂 × 赛程（可选身份后缀）。

    A3：本函数只保留给不掌握完整评价身份的旧调用方（其键与生产键格式不同，不会与
    生产实例互吞）；**生产路径一律走 av_instance_row / av_instance_identity_key**，
    因为缺候选、对手情景与面板种子的键会让两个真实实例共用一条记录。
    """

    key = "{0}|seat{1}|{2}|{3}".format(source_root_id, int(seat), arm, schedule)
    return key if identity in (None, "") else "{0}|id{1}".format(key, identity)


def av_instances_path(run_root: Path) -> Path:
    """实例任务台账路径（同一个运行目录一本台账，跨迭代累积）。"""

    return Path(run_root) / "instances.json"


def av_instances_load(run_root: Path) -> Dict[str, Any]:
    """回读实例任务台账；缺失即空台账（不伪造条目）。"""

    path = av_instances_path(run_root)
    if not path.is_file():
        return {"schema": AV_INSTANCE_SCHEMA, "instances": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or not isinstance(data.get("instances"), Mapping):
        raise ValueError("实例台账损坏，拒绝在其上继续：{0}".format(path))
    return {"schema": AV_INSTANCE_SCHEMA, "instances": dict(data["instances"])}


def _av_attempt_record(update: Mapping[str, Any], *, attempt_no: int,
                       status: str, at_utc: str) -> Dict[str, Any]:
    """一条尝试历史记录（attempt_no 是**尝试身份**：同号只能是同一次尝试）。"""

    record: Dict[str, Any] = {"attempt_no": int(attempt_no), "status": str(status),
                              "at_utc": at_utc}
    if update.get("planned_tables") is not None:
        record["planned_tables"] = update.get("planned_tables")
    if status == "completed":
        tables = int(update.get("tables") or 0)
        record["cost"] = {"tables": tables}
        record["result_digest"] = update.get("result_digest")
        record["result_path"] = update.get("result_path")
    elif status == "aborted":
        record["reason"] = update.get("reason")
    return record


def _av_attempt_payload(record: Mapping[str, Any]) -> str:
    """尝试记录的可比对载荷（时间戳不入载荷：同一次尝试重放不算新事实）。"""

    return canonical_json({key: record.get(key) for key in
                           ("attempt_no", "status", "planned_tables", "cost",
                            "result_digest", "reason")})


def _av_instances_apply_registry(registry: Dict[str, Any], *,
                                 updates: Sequence[Mapping[str, Any]],
                                 attempt_no: int, iteration_no: int,
                                 run_id: str) -> Dict[str, Any]:
    """把一批实例更新落到**一本**台账上（A3 不变量见模块内注释）。

    不变量：
      ① **先落盘后执行**：started 必须在真实副作用之前写入；
      ② **已完成记录只能幂等重读**：同一实例的 completed 摘要一经落账不得覆写，
         也不得被 started 降级（复审 A3：completed → started 会顶掉已完成结果）；
      ③ **尝试身份唯一**：同一 attempt_no 的历史只能沿 started → 终态推进一次；
         同号重放是幂等，同号改写成另一个事实是冲突（历史不被替换）；
      ④ **真重试另起尝试编号**并保留全部历史（旧尝试记录与已完成摘要都不动）；
      ⑤ **同键不同身份是冲突**：候选/情景/种子/根/座位/臂/赛程任何一维不符即
         拒绝登记，绝不静默把两条不同任务并成一条。
    """

    rows = registry["instances"]
    report: Dict[str, List[Any]] = {"started": [], "completed": [], "aborted": [],
                                    "conflicts": [], "idempotent": [],
                                    "retained_completed": []}
    for update in updates:
        key = str(update.get("instance_key") or "")
        status = str(update.get("status") or "")
        if not key:
            report["conflicts"].append({"reason": "实例缺 instance_key（不登记无名任务）",
                                        "incoming": dict(update)})
            continue
        if status not in ("started", "completed", "aborted"):
            raise ValueError("未知实例状态 {0!r}".format(status))
        row = dict(rows.get(key) or {})
        row.setdefault("instance_key", key)
        mismatch = [field for field in AV_INSTANCE_ROW_IDENTITY_FIELDS
                    if update.get(field) is not None and row.get(field) is not None
                    and canonical_json(row.get(field))
                    != canonical_json(update.get(field))]
        if mismatch:
            report["conflicts"].append({
                "instance_key": key, "reason": "同键身份不符（不合并两条不同任务）",
                "fields": {field: {"recorded": row.get(field),
                                   "incoming": update.get(field)}
                           for field in mismatch}})
            continue
        for field_name in AV_INSTANCE_ROW_IDENTITY_FIELDS:
            if update.get(field_name) is not None:
                row[field_name] = update.get(field_name)
        at_utc = utc_now()
        attempts = [dict(item) for item in (row.get("attempts") or [])]
        index = next((position for position, item in enumerate(attempts)
                      if int(item.get("attempt_no") or 0) == int(attempt_no)), None)
        incoming = _av_attempt_record(update, attempt_no=attempt_no, status=status,
                                      at_utc=at_utc)
        if index is not None:
            recorded_attempt = attempts[index]
            if _av_attempt_payload(recorded_attempt) == _av_attempt_payload(incoming):
                # 同一次尝试的同一种事实重放：一个字都不改（幂等重读）。
                report["idempotent"].append(key)
                continue
            if not (str(recorded_attempt.get("status")) == "started"
                    and status in AV_INSTANCE_TERMINAL_STATUSES):
                report["conflicts"].append({
                    "instance_key": key,
                    "reason": ("尝试 {0} 已记 {1}，不得在同一尝试身份上改成 {2}"
                               "（历史不被替换；真重试请用新的 attempt_no）").format(
                                   int(attempt_no), recorded_attempt.get("status"),
                                   status),
                    "existing": dict(recorded_attempt), "incoming": dict(incoming)})
                continue
            # started → 终态：同一次尝试的状态推进，保留起步时刻（不丢历史）。
            merged = dict(incoming)
            merged["at_utc"] = recorded_attempt.get("at_utc") or at_utc
            attempts[index] = merged
        else:
            attempts.append(incoming)
        row["attempts"] = attempts
        completed = row.get("completed")
        if status == "started":
            if completed:
                # ②：已有完成记录 → 只记本次重试，不降级、不擦结果。
                row["retry_attempt_no"] = int(attempt_no)
                row["retry_started_at_utc"] = at_utc
                report["retained_completed"].append(key)
            else:
                row["status"] = "started"
                row["attempt_no"] = int(attempt_no)
                row["started_at_utc"] = at_utc
            row["iteration_no"] = int(iteration_no)
            row["run_id"] = run_id
            report["started"].append(key)
        elif status == "completed":
            digest = update.get("result_digest")
            if completed and canonical_json(completed.get("result_digest")) !=                     canonical_json(digest):
                report["conflicts"].append({
                    "instance_key": key,
                    "reason": "同一实例重复评价出不同结果摘要（已完成记录不得覆写）",
                    "existing": completed.get("result_digest"), "incoming": digest})
                continue
            if not completed:
                record = {"attempt_no": int(attempt_no),
                          "result_digest": digest,
                          "result_path": update.get("result_path"),
                          "tables": int(update.get("tables") or 0),
                          "completed_at_utc": at_utc}
                row["completed"] = record
                row["status"] = "completed"
                row["attempt_no"] = int(attempt_no)
                row["completed_at_utc"] = at_utc
                row["cost"] = {"tables": record["tables"]}
                row["result_digest"] = digest
                row["result_path"] = update.get("result_path")
                row["iteration_no"] = int(iteration_no)
                row["run_id"] = run_id
            report["completed"].append(key)
        else:
            if not completed and str(row.get("status")) != "completed":
                row["status"] = "aborted"
                row["aborted_reason"] = update.get("reason")
            row["iteration_no"] = int(iteration_no)
            row["run_id"] = run_id
            report["aborted"].append(key)
        rows[key] = row
    return report


def av_instances_apply(registry_root: Path, *, updates: Sequence[Mapping[str, Any]],
                       attempt_no: int, iteration_no: int, run_id: str,
                       mirror_root: Optional[Path] = None) -> Dict[str, Any]:
    """按实例落台账：started（副作用之前）/ completed（费用+不可变摘要）/ aborted。

    A3：**台账按迭代隔离**——生产调用以迭代目录为 registry_root（iter_dir/
    instances.json 是本次迭代的事务面）；同时把同一批更新镜像到 running 级累计台账
    （mirror_root = 运行目录），跨迭代审计视图与既有消费者口径不变。两份都走同一条
    不变量实现，任一份的冲突都如实上报，不互相顶替。
    """

    registry = av_instances_load(registry_root)
    report = _av_instances_apply_registry(registry, updates=updates,
                                          attempt_no=attempt_no,
                                          iteration_no=iteration_no, run_id=run_id)
    av_atomic_write_json(av_instances_path(registry_root), registry)
    report["registry_path"] = str(av_instances_path(registry_root))
    report["n_instances"] = len(registry["instances"])
    if mirror_root is not None and Path(mirror_root) != Path(registry_root):
        mirror = av_instances_load(mirror_root)
        mirror_report = _av_instances_apply_registry(
            mirror, updates=updates, attempt_no=attempt_no,
            iteration_no=iteration_no, run_id=run_id)
        av_atomic_write_json(av_instances_path(mirror_root), mirror)
        report["mirror"] = {"registry_path": str(av_instances_path(mirror_root)),
                            "n_instances": len(mirror["instances"]),
                            "conflicts": list(mirror_report["conflicts"]),
                            "idempotent": list(mirror_report["idempotent"])}
    return report


def av_checkpoint_path(iter_dir: Path, name: str) -> Path:
    """迭代目录内的检查点路径（显式恢复对账面，不只当记录写）。"""

    return Path(iter_dir) / "checkpoints" / (str(name) + ".json")


def av_checkpoint_load(iter_dir: Path, name: str) -> Optional[Dict[str, Any]]:
    """回读检查点；缺失/损坏返回 None（损坏即视为未完成：重跑并留证据）。"""

    path = av_checkpoint_path(iter_dir, name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dict(data) if isinstance(data, Mapping) else None


def av_checkpoint_write(iter_dir: Path, name: str, payload: Mapping[str, Any]) -> Path:
    """原子写检查点（S3）。"""

    path = av_checkpoint_path(iter_dir, name)
    av_atomic_write_json(path, dict(payload, schema=AV_CHECKPOINT_SCHEMA,
                                    updated_at_utc=utc_now()))
    return path


def av_checkpoint_result_matches(checkpoint: Optional[Mapping[str, Any]],
                                 result_path: Path) -> bool:
    """检查点声明的不可变结果摘要是否与实际文件一致（复用判据）。"""

    if not checkpoint or str(checkpoint.get("status")) != "completed":
        return False
    recorded = checkpoint.get("result_sha256")
    target = Path(result_path)
    if not recorded or not target.is_file():
        return False
    return str(recorded) == _av_file_digest(target)


def av_real_table_fail_closed(authorization: Optional[Mapping[str, Any]] = None, *,
                              operation: str = "evaluate") -> None:
    """零预算红线：无**受信**授权时拒绝任何真实桌赛执行（fail-closed，Q6 统一入口）。

    判据不再是"authorized is True"这一条：走 av_authorization_allows 逐项校验
    （形态/trusted/操作允许/批次标签/账户声明），任何一项不满足即抛 BudgetExhausted，
    拒绝原文里带具名原因（便于运行审计与人复核）。
    """

    ok, reason, _verdict = av_authorization_allows(
        authorization, operation=operation,
        required=AV_AUTHORIZATION_OPERATION_REQUIREMENTS.get(operation))
    if ok:
        return
    raise BudgetExhausted(
        "无真实桌赛授权（Q6 统一受信校验未通过）：{0}。面板/续打一律走 "
        "scripted_fixture 离线夹具（真实桌赛实例恒 0）；获得新授权后需新账本与"
        "新面板身份，不得把夹具结果冒充真实结果".format(reason))


# ---------------------------------------------------------------------------
# 9.1 validate-contract：两份合同 JSON + 与执行器对账
# ---------------------------------------------------------------------------


def validate_action_value_contracts(*, action_value_path: Optional[Path] = None,
                                    group_dev_path: Optional[Path] = None) -> Dict[str, Any]:
    """校验 contracts/*.json 两份合同并与执行器对账（§13.1 validate-contract）。

    对账项：白名单、限额、入口签名、门禁 schema、worker 上限常量——
    合同 JSON 与 B2 执行器实际校验值必须一致（同源，不两套）。任何一项
    不一致即 ok=False（旧 delta 身份、新分数签名冲突拒绝）。
    """

    repo = REPO_ROOT
    av_path = action_value_path or (repo / "review/llm-guided-heuristic-route-2026-09-15"
                                    / "contracts/action-value-v1.json")
    gd_path = group_dev_path or (repo / "review/llm-guided-heuristic-route-2026-09-15"
                                 / "contracts/group-dev-v1.json")
    problems: List[str] = []
    checks: Dict[str, Any] = {}
    contract = json.loads(Path(av_path).read_text(encoding="utf-8"))
    group = json.loads(Path(gd_path).read_text(encoding="utf-8"))

    checks["action_value_contract"] = {
        "path": str(av_path),
        "schema": contract.get("schema"),
        "candidate_kind": contract.get("candidate_kind"),
    }
    if contract.get("schema") != "sitin-action-value-contract/1":
        problems.append("action-value 合同 schema 不是 sitin-action-value-contract/1")
    if contract.get("candidate_kind") != "action_value_v1":
        problems.append("candidate_kind 必须是 action_value_v1")
    checks["group_dev_contract"] = {
        "path": str(gd_path),
        "schema": group.get("schema"),
        "target_id": (group.get("objective") or {}).get("target_id"),
    }
    if (group.get("objective") or {}).get("target_id") != "group_advance_v1":
        problems.append("目标合同的 target_id 必须是 group_advance_v1")

    from hangma_bot.policy import action_value_executor as executor
    whitelist = contract.get("whitelist") or {}

    def _method_name(item: str) -> str:
        # JSON 条目形如 ".append(仅局部构造期)"：剥掉前导点与括注后对账。
        return str(item).split("(")[0].strip().lstrip(".")

    checks["executor_whitelist_reconciled"] = {
        "builtins_match": set(whitelist.get("builtins") or ()) == set(executor.ALLOWED_BUILTINS),
        "methods_match": ({_method_name(item) for item in whitelist.get("methods_readonly") or ()}
                          >= set(executor.ALLOWED_METHODS)),
    }
    if not checks["executor_whitelist_reconciled"]["builtins_match"]:
        problems.append("合同白名单 builtins 与执行器 ALLOWED_BUILTINS 不一致（同源破坏）")
    if not checks["executor_whitelist_reconciled"]["methods_match"]:
        problems.append("合同只读方法白名单未覆盖执行器 ALLOWED_METHODS")

    limits = (contract.get("limits") or {}).get("candidate") or {}
    expected_limits = {
        "max_counted_operations": executor.MAX_COUNTED_OPERATIONS,
        "max_local_collection_size": executor.MAX_LOCAL_COLLECTION_SIZE,
        "max_source_bytes": executor.MAX_SOURCE_BYTES,
    }
    limit_match = {key: (limits.get(key) == value)
                   for key, value in expected_limits.items()}
    checks["executor_limits_reconciled"] = limit_match
    for key, matched in limit_match.items():
        if not matched:
            problems.append("限额 {0}：合同 {1!r} 与执行器 {2!r} 不一致".format(
                key, limits.get(key), expected_limits[key]))

    entry = (contract.get("entry_point") or {}).get("signature") or ""
    checks["entry_signature_reconciled"] = {
        "signature": entry,
        "score_actions_required": "score_actions" in entry and "(view" in entry,
    }
    if not checks["entry_signature_reconciled"]["score_actions_required"]:
        problems.append("入口签名必须是 score_actions(view) 形式")

    gates = av_gates()
    checks["admission_schema_reconciled"] = {
        "contract": contract.get("admission_record_schema"),
        "gates": gates.AV_ADMISSION_SCHEMA,
        "match": contract.get("admission_record_schema") == gates.AV_ADMISSION_SCHEMA,
    }
    if not checks["admission_schema_reconciled"]["match"]:
        problems.append("合同 admission_record_schema 与门禁常量不一致")
    checks["worker_cap_reconciled"] = {
        "contract_side": AV_MAX_WORKERS, "gates_side": gates.AV_MAX_WORKERS,
        "match": AV_MAX_WORKERS == gates.AV_MAX_WORKERS,
    }
    if not checks["worker_cap_reconciled"]["match"]:
        problems.append("全机工作进程上限常量两处不一致")

    gen = av_generate()
    checks["delta_signature_conflict_guard"] = {
        "delta_entry": gen.ENTRY_NAME, "action_value_entry": gen.AV_ENTRY_NAME,
        "distinct": gen.ENTRY_NAME != gen.AV_ENTRY_NAME,
        "note": "旧 delta 身份（build_adjustment_from_params）与新分数签名"
                "（score_actions）不同名；新路线合同不得用旧入口，反之亦然",
    }
    if not checks["delta_signature_conflict_guard"]["distinct"]:
        problems.append("新旧入口签名同名：身份冲突，拒绝")

    return {
        "schema": "sitin-action-value-contract-validation/1",
        "ok": not problems,
        "problems": problems,
        "checks": checks,
        "note": "机器检查结果；合同-执行器-渲染三方同源对账（T07/同源测试共用）",
    }


# ---------------------------------------------------------------------------
# 9.2 evaluate-action-value：admit → C1 双臂 → C2 统计/档案 → 反馈 → 调度
# ---------------------------------------------------------------------------


def _av_group_utility_for_arm(snapshot: Mapping[str, Any], final_scores,
                              focal_seat: int) -> Dict[str, Any]:
    """按 group_advance_v1 识别区间算该臂的终端 U（sitin_stage 单一实现）。"""

    stage_mod = av_stage()
    completed = (snapshot.get("stage_ledger") or {}).get("completed_table_scores") or []
    rows = []
    for seat in range(4):
        total = sum(int(row[seat]) for row in completed) + int(final_scores[seat])
        rows.append(stage_mod.LedgerRow(participant_id="seat-{0}".format(seat),
                                        total_score=total))
    return stage_mod.group_advance_utility(rows, focal_id="seat-{0}".format(focal_seat))


def _av_arm_record(arm: Mapping[str, Any], candidate_id: str, snapshot: Mapping[str, Any],
                   focal_seat: int, *, is_candidate: bool) -> Dict[str, Any]:
    """把 C1 双臂的一臂转成 C2 样本臂结构（含终端 U 识别区间；不补零）。

    R6 缺口1 修复：臂来自 build_panel 的 run_conditional_stage_arm 产物——
    优先读臂自带的 focal_policy_id（真实策略身份）与完整剩余阶段 U 区间
    （u/u_low/u_high/unresolved）；仅当臂缺这些字段（旧形状）时回退到按
    final_scores 现算的识别区间。
    """

    record: Dict[str, Any] = {
        "candidate_id": (candidate_id if is_candidate else AV_BASELINE_ID),
        "policy_id": (arm.get("focal_policy_id")
                      or ("action_value" if is_candidate else "fixture-baseline-focal")),
        "status": arm.get("status"),
        "usable": bool(arm.get("usable")),
        "error": arm.get("error"),
        "final_scores": arm.get("final_scores"),
        "elapsed_ms": arm.get("elapsed_ms"),
        # A1(d)：执行证据（运行时种类 / 执行类别 / 逐桌决策计数与完成原因）
        # 全部转写自臂执行记录，供消费方与准入程序交叉校验。
        "runtime_kind": arm.get("runtime_kind"),
        "execution_kind": arm.get("execution_kind"),
        "selection_eligible": bool(arm.get("selection_eligible")),
        "tables": [dict(table) for table in (arm.get("tables") or [])],
        "tables_executed": int(arm.get("tables_executed") or 0),
        "decisions_after_cut": arm.get("decisions_after_cut"),
        "decisions_total": int(arm.get("decisions_total") or 0),
        "completion_reasons": list(arm.get("completion_reasons") or []),
        "declared_endpoint": "stage_complete",
    }
    if not record["usable"]:
        record.update({"u": None, "u_low": None, "u_high": None})
        return record
    if arm.get("u_low") is not None or arm.get("u_high") is not None:
        # 完整剩余阶段 U（sitin_stage.group_advance_utility 识别区间）。
        u_low, u_high = float(arm["u_low"]), float(arm["u_high"])
        record.update({
            "u": (float(arm["u"]) if arm.get("u") is not None
                  else ((u_low + u_high) / 2.0 if u_low == u_high else None)),
            "u_low": u_low, "u_high": u_high,
            "unresolved": arm.get("unresolved"),
            "u_interval": arm.get("u_interval"),
        })
        return record
    if arm.get("final_scores") is None:
        record.update({"u": None, "u_low": None, "u_high": None})
        return record
    utility = _av_group_utility_for_arm(snapshot, arm["final_scores"], focal_seat)
    record.update({
        "u": (float(utility["u_low"] + utility["u_high"]) / 2.0
              if utility["u_low"] == utility["u_high"] else None),
        "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
        "unresolved": utility["unresolved"],
    })
    return record


def build_evaluation_sample(*, panel: Mapping[str, Any], double_arm: Mapping[str, Any],
                            candidate_id: str, scenario: str,
                            opponent_mix: str, fixture_mode: bool = True,
                            real_table_instances: int = 0,
                            double_table_instances: int = 0,
                            execution_kind: str = "scripted_fixture",
                            runtime_kind: Optional[str] = None) -> Dict[str, Any]:
    """把一次双臂结果组装成 C2 样本（classify_sample 可直接消费的形状）。

    fixture_mode/real_table_instances 由调用方按**实际运行时种类**如实标注：
    scripted_fixture 保持 True/0（原行为）；v2_behavior 真实运行时按被启动的
    真实桌赛实例数记；显式测试替身记 execution_kind=test_double、真实桌赛实例 0、
    替身桌数另记 double_table_instances（A1：不把替身执行冒充真实执行）。
    """

    scenarios = [item for item in panel.get("scenarios", [])
                 if item.get("status") == "sampled"]
    snapshot = scenarios[0]["snapshot"] if scenarios else {}
    focal_seat = int(panel.get("focal_seat") or 0)
    arms_raw = double_arm.get("arms") or {}
    arms = {
        "baseline": _av_arm_record(arms_raw.get("baseline") or {}, candidate_id,
                                   snapshot, focal_seat, is_candidate=False),
        "candidate": _av_arm_record(arms_raw.get("candidate") or {}, candidate_id,
                                    snapshot, focal_seat, is_candidate=True),
    }
    descriptor = snapshot.get("root_descriptor")
    sample: Dict[str, Any] = {
        "schema": "sitin-action-value-sample/1",
        "source_root_id": snapshot.get("source_root_id"),
        "candidate_id": candidate_id,
        "scenario": scenario,
        "opponent_mix": opponent_mix,
        "arms": arms,
        "completeness": "complete" if double_arm.get("valid") else "invalid",
        "invalid_reasons": [arm["error"] for arm in arms.values() if arm.get("error")],
        "cost": {"elapsed_ms": sum(float(arm.get("elapsed_ms") or 0.0)
                                   for arm in arms_raw.values())},
        "fixture_mode": bool(fixture_mode),
        "real_table_instances": int(real_table_instances),
        "double_table_instances": int(double_table_instances),
        "execution_kind": str(execution_kind),
        "runtime_kind": runtime_kind,
        # 只有真实运行时的样本可用于开发选留/效果反馈（A1 验收）。
        "selection_eligible": (str(execution_kind) == "real_runtime"),
    }
    if isinstance(descriptor, Mapping) and descriptor.get("root_id"):
        # A3：样本自带**根描述符**（普通生成时写进快照）——家族登记直接取这里的真实
        # 执行种子，不再由登记方另算一套派生式；候选身份不进描述符（评价实例另计）。
        sample["root_descriptor"] = dict(descriptor)
        sample["root_id"] = str(descriptor["root_id"])
        sample["root_index"] = int(descriptor["root_index"])
        sample["root_seed"] = int(descriptor["root_seed"])
    return sample


def evaluation_identity(*, candidate_id: str, target_contract_sha256: str,
                        opponent_mix: str, source_root_id: Optional[str],
                        panel_generator: str, execution_kind: str = "scripted_fixture",
                        endpoint: str = "stage_complete") -> str:
    """§6.3 evaluation_id：目标合同+候选/基线+对手+面板/来源根+执行类别+终点。

    A1：身份里带**执行类别**（真实运行时 / 验证替身 / 脚本夹具）与终点，替身
    路由与真实路由不会得到同一个 evaluation_id——恢复/复用时不会把替身结果
    当成真实结果（身份不同即新评价，不续写旧结果）。
    """

    return sha256_text(canonical_json({
        "target_contract_sha256": target_contract_sha256,
        "candidate_id": candidate_id, "baseline_id": AV_BASELINE_ID,
        "opponent_mix": opponent_mix, "source_root_id": source_root_id,
        "panel_generator": panel_generator, "statistics_version": "sitin-paired-stage-stats/1",
        "execution_kind": str(execution_kind),
        "endpoint": str(endpoint),
    }))


def build_three_segment_feedback(evaluation: Optional[Mapping[str, Any]] = None,
                                 *, eval_dir: Optional[Path] = None,
                                 parent_cid: Optional[str] = None,
                                 candidate_cid: Optional[str] = None
                                 ) -> Dict[str, Any]:
    """§8.2 三段反馈投影：**统一走 `tools/sitin_feedback.py`**（R7/P9 修复）。

    旧实现（冻结提交）在本函数里自建反馈：`panels` 下一层就是情景名，代码却取
    `block["n_roots"]/`block["status"]`（真值在 `block["panels"]["H"]`），覆盖层又取
    `admission.layers.coverage.status`（该块没有 `layers` 键），于是 5/5 提案的反馈
    恒为 `mean_delta=None, n_roots=None, status=None` 与「覆盖层：None」，并被渲染进
    M1 提示词驱动作者改动；机制段还填死了固定猜测。现在一律由共享投影从**验证过的
    产物**生成，逐条带证据（产物路径 + JSON 定位 + 原值），机制段只留模型假设槽位。

    - `eval_dir`：产物目录（含 `evaluation.json` / `panel-<谓词>/panel.json` /
      `natural-<mix>/panel.json` / `summary/statistics.json`）。**必须给出**——
      没有产物的"内存反馈"正是缺陷来源；给不出即拒绝（executable=False）。
    - `evaluation`：可选；仅用于在 `eval_dir` 缺 `evaluation.json` 时提供身份线索，
      不参与任何数字（数字一律读自产物）。
    """

    feedback = av_feedback()
    resolved_dir = Path(eval_dir) if eval_dir is not None else None
    if resolved_dir is None:
        return _refused_feedback_projection(
            "没有给出评估产物目录（eval_dir）：拒绝生成无产物的反馈")
    if candidate_cid is None and evaluation is not None:
        candidate_cid = (_mapping_or_empty(evaluation.get("identity"))
                         .get("candidate_id"))
    try:
        inputs = feedback.collect_feedback_inputs(
            resolved_dir, parent_cid=parent_cid, candidate_cid=candidate_cid)
    except feedback.FeedbackInputError as error:
        return _refused_feedback_projection(str(error))
    return feedback.build_feedback_projection(inputs)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _refused_feedback_projection(reason: str) -> Dict[str, Any]:
    """拒绝形态的三段反馈（结构与投影一致，`executable=False`）。"""

    feedback = av_feedback()
    mechanism = feedback.FIELD_NOT_READING_NOTE
    return {
        "schema": feedback.PROJECTION_SCHEMA,
        "status": feedback.PROJECTION_REFUSED,
        "executable": False,
        "refusals": [{"code": "input.artifacts_missing", "detail": str(reason)}],
        "gaps": [],
        "identity": {},
        "facts": [str(reason)],
        "associated_results": [],
        "mechanism_hypothesis": mechanism,
        "boundary": ("未做单动作反事实实验；反馈只含开发结果与来源根/窗口，"
                     "**不含确认集数据**。程序不推算、不补零、不判定优胜。"),
        "facts_items": [],
        "result_items": [],
        "mechanism_slots": {"rule": feedback.MECHANISM_RULE, "fields": [],
                            "fields_source": "unbound_candidate_source",
                            "readings_collected": False,
                            "readings_note": mechanism, "direction_slots": 0,
                            "text": mechanism},
        "reconciliation": [],
    }


def group_dev_contract_path() -> Path:
    """group-dev-v1 冻结合同路径（对手情景/每阶段桌数/每桌单局数的单一事实源）。"""

    return (_project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
            / "contracts/group-dev-v1.json"))


def admit_evaluation_result(evaluation: Mapping[str, Any], *,
                           panel: Mapping[str, Any]) -> Dict[str, Any]:
    """结果准入交叉校验（A1(d)）：同一产物不得自相矛盾，且必须可核对执行证据。

    逐条核对（任一不通过即 ok=False，调用方据此拒绝进入选留/反馈）：
    1. 面板与评估的执行类别 / 引擎种类一致；
    2. 面板红线的真实桌赛实例数 == 评估的 real_table_instances（**同一读数**）；
    3. 「真实完成」必须同时满足：execution_kind=real_runtime、
       engine_kind=simulation_engine_public、real_table_instances ≥ 1、
       tables_partial 计费 == 该实例数（费用来自执行记录）；
    4. 「零真实桌赛」（替身/夹具）不得声明可用于开发选留或强度证据；
    5. 逐臂逐桌执行记录必须带决策计数与完成原因，且合计对得上（真实执行时 > 0）；
    6. 夹具路由必须 fixture_mode=True 且零真实桌赛。
    """

    EP = av_opportunities()
    problems: List[str] = []
    checks: Dict[str, Any] = {}
    execution_kind = str(evaluation.get("execution_kind"))
    engine_kind = str(evaluation.get("engine_kind"))
    real_instances = int(evaluation.get("real_table_instances") or 0)
    double_instances = int(evaluation.get("double_table_instances") or 0)
    panel_kind = str(panel.get("execution_kind"))
    red_line = panel.get("budget_red_line") or {}
    red_started = int(red_line.get("real_table_instances_started") or 0)
    prefix_source = str(evaluation.get("prefix_source"))
    checks["execution_kind"] = execution_kind
    checks["engine_kind"] = engine_kind
    checks["real_table_instances"] = real_instances
    checks["panel_real_table_instances_started"] = red_started

    if panel_kind != execution_kind:
        problems.append("面板执行类别 {0!r} 与评估执行类别 {1!r} 不一致".format(
            panel_kind, execution_kind))
    if str(panel.get("engine_kind")) != engine_kind:
        problems.append("面板引擎种类 {0!r} 与评估引擎种类 {1!r} 不一致".format(
            panel.get("engine_kind"), engine_kind))
    if red_started != real_instances:
        problems.append(
            "面板红线的真实桌赛实例 {0} 与评估 real_table_instances {1} 不一致"
            "（两处读数必须同源）".format(red_started, real_instances))

    is_real = execution_kind == EP.EXECUTION_REAL
    if is_real:
        if engine_kind != "simulation_engine_public":
            problems.append(
                "声明真实执行（real_runtime）却用引擎种类 {0!r}：真实执行必须是"
                "组合根 SimulationEngine".format(engine_kind))
        if real_instances < 1:
            problems.append(
                "同一产物同时声明「零真实桌赛」（real_table_instances=0 / 面板红线 "
                "{0}）与「真实完成」（execution_kind=real_runtime 且 ok={1}）"
                "——A1 禁止".format(red_started, evaluation.get("ok")))
        charged = float(evaluation.get("tables_partial_charged") or 0.0)
        if abs(charged - float(real_instances)) > 1e-9:
            problems.append(
                "tables_partial 计费 {0} 与执行记录的真实桌赛实例 {1} 不一致".format(
                    charged, real_instances))
    else:
        if real_instances != 0:
            problems.append(
                "非真实执行（{0}）却声明真实桌赛实例 {1}：不得把替身/夹具执行"
                "标成真实桌赛".format(execution_kind, real_instances))
        if evaluation.get("usable_for_selection"):
            problems.append(
                "非真实执行（{0}）声明可参与开发选留（usable_for_selection=True）："
                "替身/夹具结果不得进入选留与效果反馈".format(execution_kind))
        if evaluation.get("strength_evidence"):
            problems.append("非真实执行（{0}）声明强度证据（strength_evidence=True）".format(
                execution_kind))
        if execution_kind == EP.EXECUTION_TEST_DOUBLE and not evaluation.get(
                "double_table_instances"):
            problems.append("替身执行未记录替身桌数（double_table_instances 缺失或 0）")

    if prefix_source == "scripted_fixture":
        if execution_kind != EP.EXECUTION_SCRIPTED_FIXTURE:
            problems.append("夹具前缀路由的执行类别必须是 scripted_fixture，得到 {0!r}".format(
                execution_kind))
        if not evaluation.get("fixture_mode"):
            problems.append("夹具前缀路由必须 fixture_mode=True")
        if real_instances != 0:
            problems.append("夹具前缀路由的真实桌赛实例必须为 0")

    # 逐臂逐桌执行记录（决策计数 / 完成原因一律来自执行记录）。
    arms = ((evaluation.get("double_arm") or {}).get("arms") or {})
    audit_schema = (evaluation.get("identity") or {}).get("policy_execution_schema")
    audit_mod = _sibling("sitin_execution_audit")
    profiles = _sibling("sitin_execution_profile")
    if audit_schema is not None and audit_schema != audit_mod.SCHEMA:
        problems.append("条件评分审计版本不符")
    if audit_schema is not None:
        try:
            profiles.require_same(evaluation.get("candidate_execution_profile"),
                (evaluation.get("identity") or {}).get("candidate_execution_profile"))
        except ValueError as error:
            problems.append("条件执行身份错误：" + str(error))
    per_arm: Dict[str, Any] = {}
    for name, arm in arms.items():
        tables = list(arm.get("tables") or [])
        if audit_schema is not None:
            try:
                actual_review = audit_mod.review_tables(tables)
                if arm.get("execution_review") != actual_review:
                    raise ValueError("条件阶段评分执行汇总不符")
                if prefix_source == "v2_behavior":
                    for table in tables:
                        profiles.verify_table(table,
                            profile=evaluation.get("candidate_execution_profile"),
                            candidate_seat=0 if name == "candidate" else None)
            except ValueError as error:
                problems.append("{0} 臂评分审计错误：{1}".format(name, error))
        decisions = [table.get("decisions") for table in tables]
        reasons = [table.get("completion_reason") for table in tables]
        per_arm[name] = {"tables": len(tables), "decisions": decisions,
                         "completion_reasons": reasons,
                         "execution_kind": arm.get("execution_kind")}
        if tables and any(value is None for value in decisions):
            problems.append("{0} 臂存在缺决策计数的桌（执行记录不完整）".format(name))
        if tables and any(not value for value in reasons):
            problems.append("{0} 臂存在缺完成原因的桌（执行记录不完整）".format(name))
        if tables and sum(int(value or 0) for value in decisions) != int(
                arm.get("decisions_total") or 0):
            problems.append("{0} 臂逐桌决策计数合计与 decisions_total 不一致".format(name))
        if is_real and tables and int(arm.get("decisions_total") or 0) < 1:
            problems.append("{0} 臂真实执行却零决策（执行记录不可信）".format(name))
        if is_real and arm.get("execution_kind") != EP.EXECUTION_REAL:
            problems.append("{0} 臂执行类别 {1!r} 与样本声明 {2!r} 不一致".format(
                name, arm.get("execution_kind"), execution_kind))
    checks["arms"] = per_arm
    return {"ok": not problems, "problems": problems, "checks": checks}


# 说明（A1 修复）：旧函数 _av_offline_runtime_double() 已删除。它曾在
# run_av_evaluation 里作为 v2_behavior 的**缺省运行时**注入公开契约验证替身，
# 使自动条件评价在元数据上冒充真实执行（复审 A1）。替身现在只能经显式测试
# 入口 sitin_opportunities.build_test_runtime_double(...) 装配，并经
# run_av_evaluation(test_runtime=...) 或状态机 test_runtime_factory 显式传入。


def run_av_evaluation(out_dir: Path, candidate_source: str, *,
                      predicate: str = "branch_open", opponent: str = "H",
                      ledger: Optional[ActionValueLedger] = None,
                      admission: Optional[Mapping[str, Any]] = None,
                      authorization: Optional[Mapping[str, Any]] = None,
                      attempts_cap: int = 8,
                      panel_seed: int = 20260916,
                      real_tables: bool = False,
                      prefix_source: str = "scripted_fixture",
                      runtime: Optional[Mapping[str, Any]] = None,
                      test_runtime: Optional[Mapping[str, Any]] = None,
                      step_token: Optional[str] = None,
                      root_indexes: Optional[Sequence[int]] = None,
                      root_seed: Optional[int] = None) -> Dict[str, Any]:
    """evaluate-action-value：admit → C1 双臂 → C2 统计 → 反馈（离线路由验收）。

    step_token（P7c）：账步标识的**任务/选择集记号**。同一（候选 × 谓词）在
    不同迭代/不同选择集上的评价是不同任务身份（家族通道跨迭代补另一侧、声明批
    物化都必须可分），缺省 None 时账步标识与既有格式**逐字一致**（既有账目与
    测试不受影响）。

    prefix_source 透传 C1 build-panel：缺省 scripted_fixture 原行为不变（夹具，
    真实桌赛实例恒 0）；"v2_behavior" 走批次 7 授权前缀路由——授权令牌沿用
    authorization 参数对象（authorized=true 且 batch=7），账本按 v4 §11 记
    tables_partial（每个被启动的**真实**桌赛实例扣 1，先按 attempts_cap 预留后
    按实结算），attempts 计数如实落账。

    运行时装配（A1 修复，复审 P1）：
    - runtime：**真实运行时**（sitin_opportunities.build_real_runtime 装配，带
      runtime_kind=real_simulation_engine 标签）；正式 CLI/状态机在组合处显式
      传入；
    - test_runtime：**显式测试入口**（build_test_runtime_double 装配的公开契约
      验证替身，runtime_kind=test_double_runtime）；只有测试传入；
    - 两者互斥；v2_behavior 下**都缺即拒绝**（RuntimeAssemblyError，fail-closed）
      ——旧实现的"缺省注入替身"已删除，替身在正式路径不可达；
    - 产物按实际运行时种类标注 execution_kind/engine_kind（真实运行时不再被
      误标成替身），真实桌赛实例数从执行记录读数；替身/夹具结果
      usable_for_selection=False（不得参与开发选留与效果反馈）；
    - 末尾经 admit_evaluation_result 交叉校验：同一产物不得同时声明
      「零真实桌赛」与「真实完成」，不通过即 ok=False + refused。

    root_indexes / root_seed（A2 修复）：**显式根选择**。缺省 None = 既有行为逐字
    不变（前缀循环取首命中根）。给出时：只启动**被选的那一个根**（单次
    run_prefix_attempt / run_real_prefix_attempt，根序号 = 根身份字段 root{NNN}），
    根序号必须在 0..AV_FAMILY_ROOT_INDEX_MAX 内、且必须同时给出该根的复现种子
    （root_seed，家族通道由 av_family_root_seed 派生并登记）——根选择与种子一起
    构成"跑的是哪个根"的任务身份，缺一即拒绝（在任何副作用之前，不猜）。
    """

    # A2：根选择在任何副作用（建目录/预留费用/启动桌赛）**之前**校验并解出。
    root_selection = av_conditional_root_selection(root_indexes)
    execution_profiles = _sibling("sitin_execution_profile")
    profile = execution_profiles.from_authorization(authorization)
    if profile["research_only"] and prefix_source != "v2_behavior":
        raise ValueError("研究额度仅支持真实候选策略接线的v2_behavior条件入口")
    if admission is not None:
        execution_profiles.require_same(admission.get("execution_profile"), profile)
    if root_selection is None:
        if root_seed is not None:
            raise ValueError("只给根种子而不选根没有意义（根种子是某个根的复现参数）："
                             "请同时给出 root_indexes")
    elif root_seed is None or isinstance(root_seed, bool) \
            or not isinstance(root_seed, int):
        raise ValueError("显式选根必须同时给出该根的复现种子 root_seed（int）："
                         "不猜复现参数（缺种子就无法复现同一牌山）")
    out_dir = guard_out_dir(Path(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    # Q3：缺省账本从授权令牌读开发账户授权额度（无 budgets 则正数记账 fail-closed）。
    ledger = ledger or ActionValueLedger(
        out_dir / "av-ledger.json",
        authorized_budgets=av_ledger_budgets_from_authorization(authorization))
    gates = av_gates()
    opp = av_archive_mod = av_archive()
    opportunities = av_opportunities()
    if admission is None:
        admission = gates.admit_action_value(
            candidate_source,
            **({"execution_profile": profile} if profile["research_only"] else {}),
            facts_panel={"generator": opportunities.GENERATOR_SCRIPTED_FIXTURE,
                        "legal": True})
    execution_profiles.require_same(admission.get("execution_profile"), profile)
    if profile["research_only"]:
        matched, why = gates.av_record_identity_matches(
            admission, candidate_source, execution_profile=profile)
        if not matched:
            raise ValueError("研究配置与条件准入身份不符：" + why)
    candidate_id = admission["identity"]["candidate_id"]
    steps: List[Dict[str, Any]] = []

    def step(name: str, status: str, **fields: Any) -> None:
        steps.append({"step": name, "status": status, **fields})

    step("admission", "PASS" if admission["execution_safety_pass"] else "FAIL",
         execution_safety=admission["layers"]["execution_safety"]["status"],
         coverage=admission["layers"]["coverage"]["status"])
    if not admission["execution_safety_pass"]:
        result = {"schema": AV_EVALUATION_SCHEMA, "ok": False,
                  "refused": "执行安全层未通过，禁止效果执行（fail-closed）",
                  "admission": admission, "steps": steps}
        write_json(out_dir / "evaluation.json", result)
        return result

    # 前缀来源校验：只有两条合法路由；v2_behavior 视同真实模式（授权 fail-closed）。
    if prefix_source not in ("scripted_fixture", "v2_behavior"):
        raise ValueError(
            "prefix_source 必须是 scripted_fixture/v2_behavior 之一，得到 {0!r}".format(
                prefix_source))
    # 零预算红线：本包评估走夹具面板（真实桌赛实例恒 0）；仅当显式请求
    # 真实桌赛或 v2_behavior 前缀路由时检查授权——无授权即 fail-closed。
    if real_tables or prefix_source == "v2_behavior":
        av_real_table_fail_closed(authorization)
    # A1 修复：v2_behavior 运行时**必须在组合处显式装配**——缺省不再注入替身。
    # 真实运行时经 runtime 传入（build_real_runtime）；测试替身只能经 test_runtime
    # 参数（显式测试入口）传入，两条路互斥且各自要求对应标签。
    effective_runtime: Optional[Mapping[str, Any]] = None
    execution_kind = opportunities.EXECUTION_SCRIPTED_FIXTURE
    runtime_kind: Optional[str] = opportunities.RUNTIME_KIND_FIXTURE
    engine_kind = opportunities.ENGINE_KIND_BY_RUNTIME_KIND[opportunities.RUNTIME_KIND_FIXTURE]
    if prefix_source == "v2_behavior":
        if runtime is not None and test_runtime is not None:
            raise ValueError(
                "runtime 与 test_runtime 不能同时给出（真实运行时 / 显式测试替身"
                "二选一；A1）")
        if runtime is None and test_runtime is None:
            raise opportunities.RuntimeAssemblyError(
                "run_av_evaluation：v2_behavior 真实路由必须在**组合处显式装配**"
                "运行时（sitin_opportunities.build_real_runtime(rules_config=..., "
                "rounds_per_game=...)，或组合根 "
                "bootstrap.build_evaluation_runtime('matches', ...)）；缺省不再注入"
                "替身（A1 fail-closed；测试替身只能经 test_runtime 参数显式传入）")
        if test_runtime is not None:
            effective_runtime = opportunities.resolve_declared_runtime(
                test_runtime, where="run_av_evaluation(test_runtime)")
            if opportunities.runtime_kind_of(effective_runtime) != \
                    opportunities.RUNTIME_KIND_TEST_DOUBLE:
                raise opportunities.RuntimeAssemblyError(
                    "test_runtime 必须是显式测试入口 build_test_runtime_double 装配的"
                    "替身（得到 runtime_kind={0!r}）；真实运行时请用 runtime 参数".format(
                        opportunities.runtime_kind_of(effective_runtime)))
        else:
            effective_runtime = opportunities.resolve_declared_runtime(
                runtime, where="run_av_evaluation(runtime)")
            if opportunities.runtime_kind_of(effective_runtime) != \
                    opportunities.RUNTIME_KIND_REAL:
                raise opportunities.RuntimeAssemblyError(
                    "runtime 参数只接受真实运行时（build_real_runtime 装配，"
                    "runtime_kind={0!r}）；测试替身请用 test_runtime 参数".format(
                        opportunities.runtime_kind_of(effective_runtime)))
        runtime_kind = opportunities.runtime_kind_of(effective_runtime)
        execution_kind = opportunities.EXECUTION_KIND_BY_RUNTIME_KIND[str(runtime_kind)]
        engine_kind = opportunities.ENGINE_KIND_BY_RUNTIME_KIND[str(runtime_kind)]
    selection_eligible = opportunities.selection_eligible_for(runtime_kind)
    step_suffix = "" if step_token in (None, "") else ":{0}".format(step_token)
    reservation = ledger.reserve(
        step_id="evaluate:{0}:{1}{2}".format(candidate_id[:12], predicate,
                                             step_suffix),
        account="prefix_generation", amount=1.0,
                                 note=("C1 夹具前缀生成（离线；真实桌赛 0）"
                                       if prefix_source == "scripted_fixture"
                                       else "C1 v2_behavior 前缀生成（批次 7 授权；"
                                            "tables_partial 按被启动桌赛实例另记）"))
    # v4 §11 账本红线：v2_behavior 前缀生成按"每个被启动的桌赛实例扣 1"记
    # tables_partial——先按 attempts_cap 预留（先预留后执行），事后按实际启动
    # 数结算（少退多不补，attempts 计数如实另记）。
    partial_reservation = None
    if prefix_source == "v2_behavior" and selection_eligible:
        # 只有真实运行时才按"每个被启动的桌赛实例扣 1"预留 tables_partial；
        # 替身执行不启动真实桌赛，不占真实桌赛账（A1：费用账不得暗示真实执行）。
        partial_reservation = ledger.reserve(
            step_id="evaluate:{0}:{1}{2}:tables-partial".format(
                candidate_id[:12], predicate, step_suffix),
            account="tables_partial", amount=float(attempts_cap),
            note="v2_behavior 真实前缀生成预留（每被启动真实桌赛实例扣 1，上限 {0}）".format(
                attempts_cap))
    # 候选真实接线（R6 缺口1 修复）：被评候选经 ActionValueScorer 装配为
    # ActionValuePolicy，传入 build_panel 作为真实路由候选臂焦点策略；双臂
    # （基线=weighted_heuristic_v2、候选=被评候选）与完整剩余阶段续打 +
    # 阶段 U 都在 build_panel 内部执行，本函数直接消费其产物（不再用
    # 夹具替身臂重跑旧双臂）。
    from hangma_bot.policy.action_value_policy import ActionValuePolicy
    from hangma_bot.policy.action_value_seeds import ActionValueScorer

    arm_candidate_policy = None
    if prefix_source == "v2_behavior":
        arm_candidate_policy = ActionValuePolicy(ActionValueScorer("av-candidate",
            candidate_source, max_operations=profile["max_operations"]))
    # v4 §11 账本：v2_behavior 双臂完整阶段桌实例记 tables_full（先按
    # 2 臂 × tables_in_stage 预留，事后按实际执行结算；前缀启动另记
    # tables_partial）。夹具路由不记（真实桌赛实例恒 0）。
    tables_full_reservation = None
    if prefix_source == "v2_behavior" and selection_eligible:
        tables_full_reservation = ledger.reserve(
            step_id="evaluate:{0}:{1}{2}:tables-full".format(
                candidate_id[:12], predicate, step_suffix),
            account="tables_full", amount=4.0,
            note="条件双臂完整剩余阶段（真实运行时：2 臂 × 2 桌；部分桌另记 "
                 "tables_partial）")
    ledger.request_workers(2, purpose="conditional double-arm workers")
    try:
        if root_selection is None:
            panel = opportunities.build_panel(
                prefix_source=prefix_source, predicate_id=predicate, focal_seat=0,
                opponent_scenario=opponent, root_label="av-eval-{0}".format(predicate),
                out_dir=out_dir / ("panel-{0}".format(predicate)),
                ruleset_version=AV_CONDITIONAL_RULESET_VERSION,
                base_score=1, you_cai_bi_kao=False, attempts_cap=attempts_cap,
                panel_seed=panel_seed,
                authorization_token=(authorization if prefix_source == "v2_behavior"
                                     else None),
                runtime=(effective_runtime if prefix_source == "v2_behavior" else None),
                # M2：对手情景（含 M 的 V2/白守/V1）**从冻结合同**读，不用代码内
                # 字面表；前缀行为策略据此装配（并逐座位与执行记录核对）。
                contract_file=group_dev_contract_path(),
                rounds_per_game=AV_CONDITIONAL_ROUNDS_PER_GAME,
                candidate_policy=arm_candidate_policy)
        else:
            # A2：根选择非空 → 单根条件面板（只启动被冻结的那一个根）。
            panel = _av_conditional_root_panel(
                prefix_source=prefix_source, predicate_id=predicate, focal_seat=0,
                opponent_scenario=opponent, root_label="av-eval-{0}".format(predicate),
                out_dir=out_dir / ("panel-{0}".format(predicate)),
                ruleset_version=AV_CONDITIONAL_RULESET_VERSION,
                base_score=1, you_cai_bi_kao=False, attempts_cap=attempts_cap,
                panel_seed=panel_seed, root_index=int(root_selection[0]),
                root_seed=int(root_seed),
                authorization_token=(authorization if prefix_source == "v2_behavior"
                                     else None),
                runtime=(effective_runtime if prefix_source == "v2_behavior" else None),
                contract_file=group_dev_contract_path(),
                rounds_per_game=AV_CONDITIONAL_ROUNDS_PER_GAME,
                candidate_policy=arm_candidate_policy)
    finally:
        ledger.release_workers(2)
    step("panel", panel["scenarios"][0]["status"], predicate=predicate,
         prefix_attempts=panel.get("prefix_attempts"),
         execution_kind=panel.get("execution_kind"),
         engine_kind=panel.get("engine_kind"))
    # A1：桌赛实例数一律从**执行记录**读数（面板 counters.total），并按运行时
    # 种类分流——真实运行时才记"真实桌赛实例"，替身/夹具记 0（另记替身桌数）。
    panel_attempts = int((panel.get("prefix_attempts") or {}).get("total") or 0)
    runtime_kind = panel.get("runtime_kind")
    execution_kind = str(panel.get("execution_kind"))
    engine_kind = str(panel.get("engine_kind"))
    selection_eligible = opportunities.selection_eligible_for(runtime_kind)
    started_table_instances = panel_attempts if selection_eligible else 0
    double_table_instances = (panel_attempts
                              if execution_kind == opportunities.EXECUTION_TEST_DOUBLE
                              else 0)
    # 双臂完整阶段实际执行的桌实例数（当前桌部分 + 剩余完整桌，逐臂累计）。
    tables_full_executed = sum(
        int(count or 0)
        for record in panel.get("cost_ledger") or []
        for count in (record.get("tables_executed_by_arm") or {}).values())

    scenarios = [item for item in panel.get("scenarios", [])
                 if item.get("status") == "sampled"]
    samples: List[Dict[str, Any]] = []
    double_arm: Dict[str, Any] = {"valid": False,
                                  "arms": {"baseline": {"error": "未取得快照"},
                                           "candidate": {"error": "未取得快照"}}}
    if scenarios:
        # R6 缺口1 修复：直接消费 build_panel 场景内的完整阶段双臂结果
        # （真策略臂 + run_conditional_stage_arm：完整剩余桌 + 阶段 U 区间）。
        double_arm = dict(scenarios[0].get("double_arm") or {})
        samples.append(build_evaluation_sample(
            panel=panel, double_arm=double_arm, candidate_id=candidate_id,
            scenario=predicate, opponent_mix=opponent,
            fixture_mode=(prefix_source == "scripted_fixture"),
            real_table_instances=started_table_instances,
            double_table_instances=double_table_instances,
            execution_kind=execution_kind,
            runtime_kind=runtime_kind))
        if root_selection is not None:
            # A2：把"跑的是哪个根"写进样本——根序号、根种子与两层内容摘要
            # （要求摘要由冻结参数重算；内容摘要来自实际截取快照）。消费方据此
            # 在**采用结果之前**核对，而不是跑完再按根身份丢弃。
            snapshot = dict(scenarios[0].get("snapshot") or {})
            index = int(root_selection[0])
            samples[-1].update({
                "root_index": index, "root_seed": int(root_seed),
                "root_requirement_digest": av_family_root_requirement_digest(
                    prefix_source=prefix_source, predicate=predicate,
                    opponent_mix=opponent, panel_seed=panel_seed,
                    root_index=index),
                "root_content_digest": (
                    snapshot.get("root_content_digest")
                    or av_family_root_content_digest(
                        prefix_source=prefix_source, predicate=predicate,
                        opponent_mix=opponent, panel_seed=panel_seed,
                        root_index=index, snapshot=snapshot)),
            })
        step("double_arm", "valid" if double_arm.get("valid") else "invalid",
             valid=double_arm.get("valid"),
             arm_policy_ids={name: arm.get("focal_policy_id")
                             for name, arm in (double_arm.get("arms") or {}).items()})
    # —— Q3：真实内容见证落生产审计附属文件（两个入口都走这里；见
    #    av_root_witness_records 与 sitin_opportunities.root_witness）——
    root_witness_records = av_root_witness_records(
        out_dir, panel=panel, candidate_id=candidate_id, predicate=predicate,
        opponent=opponent, panel_seed=panel_seed, prefix_source=prefix_source,
        execution_kind=execution_kind, runtime_kind=runtime_kind);
    if root_witness_records:
        step("root_witness", "recorded",
             count=len(root_witness_records),
             content_digests=[record["witness"].get("content_digest")
                              for record in root_witness_records],
             sidecar=str(out_dir / AV_ROOT_WITNESS_SIDECAR))
    if tables_full_reservation is not None:
        ledger.settle(tables_full_reservation, actual=float(tables_full_executed),
                      note="条件双臂完整阶段真实执行 {0} 桌（真实前缀启动 {1} 桌另记）".format(
                          tables_full_executed, started_table_instances))
    if partial_reservation is not None:
        ledger.settle(partial_reservation, actual=float(started_table_instances),
                      note="v2_behavior 前缀实际启动桌赛实例 {0} 个（attempts={1}）".format(
                          started_table_instances, panel.get("prefix_attempts")))
    ledger.settle(reservation, actual=1.0,
                  note=("{0}前缀（attempts={1}）".format(
                      "v2_behavior" if prefix_source == "v2_behavior" else "夹具",
                      (panel.get("prefix_attempts") or {}).get("total"))))

    statistics = opp.paired_stage_statistics(samples, min_roots=1)
    step("statistics", "ok", n_samples=len(samples),
         invalid_count=statistics.get("invalid_count"))
    target_contract_sha = sha256_file(
        _project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
        "/contracts/group-dev-v1.json"))
    evaluation = {
        "schema": AV_EVALUATION_SCHEMA,
        "ok": bool(samples) and double_arm.get("valid"),
        "candidate_execution_profile": profile,
        "research_only": profile["research_only"],
        "automatic_archive_profile_supported": not profile["research_only"],
        "release_eligible": False,
        "identity": {
            "candidate_id": candidate_id,
            "evaluation_id": evaluation_identity(
                candidate_id=candidate_id, target_contract_sha256=target_contract_sha,
                opponent_mix=opponent,
                source_root_id=(samples[0]["source_root_id"] if samples else None),
                panel_generator=str(panel.get("generator")),
                execution_kind=execution_kind, endpoint="stage_complete"),
            # A1：执行类别进身份，替身/真实不会得到同一个 evaluation_id。
            "execution_kind": execution_kind,
            "engine_kind": engine_kind,
            "runtime_kind": runtime_kind,
            "baseline_id": AV_BASELINE_ID,
            "policy_execution_schema": _sibling("sitin_execution_audit").SCHEMA,
            "candidate_execution_profile": profile,
            "target_contract_sha256": target_contract_sha,
            "opponent_mix": opponent,
            "panel_epoch": "{0}@{1}".format(panel.get("generator"), predicate),
            "executor_version": admission["identity"]["executor_version"],
            "contract_sha256": admission["identity"]["contract_sha256"],
        },
        "admission": {"identity": admission["identity"],
                      "execution_safety_pass": admission["execution_safety_pass"],
                      "coverage": admission["layers"]["coverage"]},
        "panel": {"generator": panel.get("generator"),
                  "prefix_source": prefix_source,
                  "predicate": predicate, "prefix_attempts": panel.get("prefix_attempts"),
                  "prefix_attempt_errors": panel.get("prefix_attempt_errors"),
                  "engine_kind": panel.get("engine_kind"),
                  "execution_kind": panel.get("execution_kind"),
                  "runtime_kind": panel.get("runtime_kind"),
                  "engine_identity": panel.get("engine_identity"),
                  "runtime_assembly": panel.get("runtime_assembly"),
                  "prefix_behavior": panel.get("prefix_behavior"),
                  # A2：面板种子进结果面板块——盘上结果与冻结声明对账
                  # （_av_family_result_matches）必须能读到它，否则真实执行结果
                  # 会被判"面板种子不符"而全部作废。
                  "panel_seed": int(panel_seed),
                  "root_selection": panel.get("root_selection"),
                  "tables_full_executed": tables_full_executed,
                  "budget_red_line": panel.get("budget_red_line"),
                  "table_instance_basis": (
                      ("v2_behavior 路由按前缀尝试计被启动真实桌赛实例（生成器 {0}）"
                       if selection_eligible else
                       "v2_behavior 路由但运行时种类为 {1}（替身/夹具）：真实桌赛实例记 0，"
                       "替身桌数另记 double_table_instances（不得作为强度证据）").format(
                           panel.get("generator"), runtime_kind)
                      if prefix_source == "v2_behavior"
                      else "scripted_fixture 夹具面板：真实桌赛实例恒 0")},
        "double_arm": double_arm,
        "samples": samples,
        # Q3：真实捕获的根见证记录（含实例身份与见证本体；不进模型可见输入）。
        "root_witnesses": root_witness_records,
        "root_witness_sidecar": (str(out_dir / AV_ROOT_WITNESS_SIDECAR)
                                 if root_witness_records else None),
        "statistics": statistics,
        "steps": steps,
        "fixture_mode": prefix_source == "scripted_fixture",
        "prefix_source": prefix_source,
        # —— A1(c)(d)：执行证据一律来自执行记录/装配对象 ——
        "execution_kind": execution_kind,
        "runtime_kind": runtime_kind,
        "engine_kind": engine_kind,
        "engine_identity": dict((effective_runtime or {}).get("engine_identity")
                                or panel.get("engine_identity") or {}),
        "runtime_assembly": {
            "entry": (str((effective_runtime or {}).get("runtime_entry"))
                      if effective_runtime is not None else "scripted_fixture_engine"),
            "runtime_kind": runtime_kind,
            "engine_kind": engine_kind,
            "explicit_at_composition_point": bool(effective_runtime is not None
                                                  and prefix_source == "v2_behavior"),
            "note": ("A1：v2_behavior 运行时必须在组合处显式装配（build_real_runtime）；"
                     "替身只能经 test_runtime 显式测试入口传入"),
        },
        "real_table_instances": started_table_instances,
        "double_table_instances": double_table_instances,
        # A2：本次评价的根选择身份（缺省 None = 既有"首命中根"行为，逐字不变）。
        "root_selection": (None if root_selection is None else {
            "selector": "conditional_root", "indexes": [int(root_selection[0])],
            # A3：根身份来自**唯一描述符**（生成器 × 子场景 × 情景 × 实际种子 × 序号）。
            "root_ids": [av_family_root_id(
                prefix_source=prefix_source, sub_scenario=predicate,
                opponent_mix=opponent, panel_seed=panel_seed,
                root_index=int(root_selection[0]))],
            "root_seed": int(root_seed),
            "requirement_digest": av_family_root_requirement_digest(
                prefix_source=prefix_source, predicate=predicate,
                opponent_mix=opponent, panel_seed=panel_seed,
                root_index=int(root_selection[0]))}),
        "max_attempts_cap": int(attempts_cap),
        "selection_eligible": bool(selection_eligible),
        "usable_for_selection": bool(selection_eligible),
        "strength_evidence": False,
        "tables_partial_charged": (float(started_table_instances)
                                   if selection_eligible else 0.0),
    }
    # A1(d)：结果准入交叉校验——同一产物不得自相矛盾；不通过即 ok=False。
    verdict = admit_evaluation_result(evaluation, panel=panel)
    evaluation["result_admission"] = verdict
    if not verdict["ok"]:
        evaluation["ok"] = False
        evaluation["refused"] = (
            "结果准入未通过（产物自相矛盾，禁止进入选留/效果反馈）：{0}".format(
                "；".join(verdict["problems"])))
    # A5：三段反馈由**共享投影**从产物生成。先落盘 evaluation.json（以及本函数
    # 之前已落盘的机会面板 panel.json），投影读取真实产物、证据定位指向真实文件；
    # 投影结果再写回同一份 evaluation.json 供读取方复用（内容除 feedback 外一致）。
    write_json(out_dir / "evaluation.json", evaluation)
    evaluation["feedback"] = build_three_segment_feedback(
        evaluation, eval_dir=out_dir,
        candidate_cid=(evaluation.get("identity") or {}).get("candidate_id"))
    write_json(out_dir / "evaluation.json", evaluation)
    ledger.save()
    return evaluation


# ---------------------------------------------------------------------------
# 9.3 evolve-action-value：§9.4 固定顺序一迭代（离线 mock 生成路由验收）
# ---------------------------------------------------------------------------


def av_mock_model_reply(candidate_source: str, thought: str,
                        mechanism: Mapping[str, str]) -> str:
    """构造**离线 mock** 回复（EoH 三段格式；非模型输出，血缘如实标注）。"""

    fence = chr(96) * 3
    # 机制说明必须包在 {…} 里（EoH 格式；parse_model_reply 只认花括号思想）。
    return ("{" + thought + "}\n\n"
            + fence + "json\n"
            + json.dumps({key: mechanism[key]
                          for key in ("trigger", "changed_branches",
                                      "expected_direction", "counterexample")},
                         ensure_ascii=False, indent=2)
            + "\n" + fence + "\n\n"
            + fence + "python\n" + candidate_source.rstrip("\n") + "\n" + fence + "\n")


def run_av_iteration(out_dir: Path, *, seed_name: str = "efficiency_seed",
                     predicate: str = "branch_open", opponent: str = "H",
                     authorization: Optional[Mapping[str, Any]] = None,
                     archive_path: Optional[Path] = None) -> Dict[str, Any]:
    """evolve-action-value：按 §9.4 固定顺序落账的一迭代（离线路由验收）。

    生成步用离线 mock（种子源码包装成 EoH 回复；不调真实 LLM、不读私有
    凭据）；面板/统计/档案/调度分别复用 C1/C2 模块 API；每步进 steps 账，
    顺序必须与 AV_ITERATION_ORDER 完全一致。`archive_path`（CLI `--archive`）
    指共享档案；缺省按 av_discover_archive 自动发现（迭代目录链最新提交）。
    """

    out_dir = guard_out_dir(Path(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    gates = av_gates()
    gen = av_generate()
    archive_mod = av_archive()
    # Q3：迭代账本从授权令牌读授权额度（mock 演示路由同样受限额强制）。
    ledger = ActionValueLedger(
        out_dir / "av-ledger.json",
        authorized_budgets=av_ledger_budgets_from_authorization(authorization))
    from hangma_bot.policy.action_value_seeds import SEEDS

    order = list(AV_ITERATION_ORDER)
    steps: List[Dict[str, Any]] = []
    # 调度输入档案（跨迭代档案链）：显式 --archive > 自动发现 > 空档案。显式
    # 指向的文件不存在即**开工前**拒绝（fail-closed，不静默按空档案跑完再报）。
    archive_input, archive_discovery = av_discover_archive(out_dir,
                                                          explicit=archive_path)
    if archive_input is None and archive_discovery.get("source") == "explicit_missing":
        result = {"schema": AV_ITERATION_SCHEMA, "ok": False,
                  "refused": ("显式 --archive 指向的档案不存在：{0}（fail-closed："
                              "不静默回退自动发现或空档案）").format(
                                  archive_discovery.get("path")),
                  "steps": steps, "order": order}
        write_json(out_dir / "iteration.json", result)
        return result

    def step(name: str, status: str, **fields: Any) -> Dict[str, Any]:
        assert name == order[len(steps)], (
            "§9.4 顺序违约：第 {0} 步应是 {1}，实际 {2}".format(
                len(steps), order[len(steps)], name))
        entry = {"step": name, "status": status, **fields}
        steps.append(entry)
        return entry

    # 1. 读取剩余预算并预留本次最大费用（离线路由：token 0、桌 0、前缀 1）。
    ledger.reserve(step_id="iterate:budget", account="tokens_input", amount=0.0,
                   note="离线 mock 生成：真实 token 0")
    ledger.reserve(step_id="iterate:prefix", account="prefix_generation", amount=1.0,
                   note="夹具前缀生成预留")
    step("read_budget_and_reserve", "ok", tokens_input=0.0, prefix_generation=1.0)

    # 2. 选算子/父代，生成代码与四字段说明（I1 + 离线 mock 回复）。
    seed = SEEDS[seed_name]
    payload = gen.render_action_value_task_contract(
        objective_summary=gen.default_objective_summary(),
        panel_boundary="开发面板：条件机会（{0}/{1}）+ 正常阶段（group-dev-v1）".format(
            predicate, opponent),
        prompt_role="I1 初始化（离线 mock 路由验收：种子源码充当模型回复）",
        budget_note="零预算红线：不调真实 LLM、不读 .private/sitin-llm.json")
    packet = gen.build_action_value_prompt("i1", payload)
    mock_reply = av_mock_model_reply(seed.source, "种子机制（离线 mock）",
                                     dict(seed.mechanism))
    parsed = gen.parse_action_value_reply(mock_reply)
    precheck = gen.precheck_action_value_candidate(
        parsed["code"]) if parsed["code"] else {"ok": False, "problems": ["无代码"]}
    step("select_operator_and_generate", "ok" if precheck["ok"] else "fail",
         operator="i1", provenance="offline_mock_fixture",
         prompt_sha256=packet.sha256, parse_status=parsed["status"],
         precheck_ok=precheck["ok"])
    if not precheck["ok"]:
        result = {"schema": AV_ITERATION_SCHEMA, "ok": False,
                  "refused": "生成预检未通过", "steps": steps,
                  "order": order}
        write_json(out_dir / "iteration.json", result)
        return result

    candidate_source = gen.normalized_code(parsed["code"])

    # 3. 固定执行器隔离装载，安全与接口检查。
    admission = gates.admit_action_value(
        candidate_source,
        facts_panel={"generator": av_opportunities().GENERATOR_SCRIPTED_FIXTURE,
                     "legal": True,
                     "record_dir": str(out_dir / "admission")})
    step("supervised_load_and_admission",
         "PASS" if admission["execution_safety_pass"] else "FAIL",
         candidate_id=admission["identity"]["candidate_id"],
         coverage=admission["layers"]["coverage"]["status"],
         timing=admission["timing"].get("status"))

    # 4. 公共行为面板：覆盖、签名、去重（本迭代取门禁覆盖层结论）。
    step("behavior_panel_coverage", admission["layers"]["coverage"]["status"],
         views=len(admission["layers"]["coverage"].get("views") or {}))

    # 5. 条件机会面板＋正常阶段面板（离线夹具；都计真实执行账——夹具桌 0）。
    evaluation = run_av_evaluation(
        out_dir / "evaluation", candidate_source, predicate=predicate,
        opponent=opponent, ledger=ledger, admission=admission,
        authorization=authorization)
    step("opportunity_and_normal_panels",
         "ok" if evaluation.get("ok") else "insufficient",
         evaluation_id=evaluation.get("identity", {}).get("evaluation_id"),
         real_table_instances=evaluation.get("real_table_instances"))

    # 6. 来源根配对统计，生成三段反馈。
    step("root_paired_statistics", "ok",
         n_samples=len(evaluation.get("samples") or []))
    feedback = evaluation.get("feedback") or build_three_segment_feedback(
        evaluation, eval_dir=out_dir / "evaluation",
        candidate_cid=(evaluation.get("identity") or {}).get("candidate_id"))
    step("three_segment_feedback", "ok",
         segments=sorted(feedback.keys() & {"facts", "associated_results",
                                            "mechanism_hypothesis"}))

    # 7. 按通道挑战与刷新复核更新档案（C2 update-archive；不读 resolved_positive）。
    #    调度输入档案 = 显式 --archive > 自动发现（迭代目录链最新提交）> 空档案；
    #    在案条目**增量合并**，不把跨 --out 的档案链截断成单候选。
    candidate_id = admission["identity"]["candidate_id"]
    samples = evaluation.get("samples") or []
    previous_archive = (json.loads(archive_input.read_text(encoding="utf-8"))
                        if archive_input is not None else {"entries": {}, "slots": {}})
    pool = dict(previous_archive.get("entries") or {})
    if samples:
        pool[candidate_id] = archive_mod.build_archive_entry(
            candidate_id, samples, safety="PASS",
            behavior_signature=None, min_roots=1)
    archive = archive_mod.update_archive([pool[cid] for cid in sorted(pool)])
    step("archive_update", "ok", slots=archive.get("slots"),
         distinct=archive.get("distinct_candidates"))

    run_id = sha256_text(canonical_json({
        "candidate_id": candidate_id, "predicate": predicate, "opponent": opponent,
        "evaluation_id": evaluation.get("identity", {}).get("evaluation_id")}) )[:24]
    # 8. next-plan 调度记录（C2）：档案有席位 → 按通道轮转选 M1 + 父代；空档案 → I1。
    #    A4：本次提案（单迭代演示路径）先入不可变事件账本，再由**同一事件序列**生成
    #    next plan——报告与实际计划同源，不靠"少算一个提案"的巧合对齐。
    completed = bool(evaluation.get("ok"))
    av_proposal_event_append(out_dir, {
        "schema": AV_PROPOSAL_EVENT_SCHEMA,
        "proposal_no": len(_av_plan_history(out_dir)) + 1,
        "run_id": run_id, "iteration_no": 1, "iter_dir": str(out_dir),
        "operator": "I1", "planned_operator": "I1", "applied_operator": "I1",
        "parent_candidate_id": None, "channel": None, "family": None,
        "candidate_id": candidate_id,
        "status": "ITERATION_COMPLETE" if completed else "EXECUTION_FAILED",
        "terminal_status": "ITERATION_COMPLETE" if completed else "EXECUTION_FAILED",
        "failed": not completed, "duplicate": False,
        "source": "single_iteration_demo",
    })
    history = _av_plan_history(out_dir)
    plan = archive_mod.next_generation_plan(archive, history)
    step("atomic_save_and_ledger", "ok", ledger_spent=ledger.account_summary(),
         next_operator=plan.get("operator"))
    result = {
        "schema": AV_ITERATION_SCHEMA,
        "ok": bool(evaluation.get("ok")),
        "run_id": run_id,
        "order": order,
        "steps": steps,
        "identity": {
            "candidate_id": candidate_id,
            "evaluation_id": evaluation.get("identity", {}).get("evaluation_id"),
            "panel_epoch": evaluation.get("identity", {}).get("panel_epoch"),
            "contract_sha256": admission["identity"]["contract_sha256"],
            "executor_version": admission["identity"]["executor_version"],
        },
        "archive": archive,
        "archive_in": _av_archive_in_record(archive_input, archive_discovery,
                                            archive, history, plan),
        "next_plan": plan,
        "ledger": ledger.to_json(),
        "boundary": "离线 mock 迭代：验证路由与账目，不构成真实进化证据（T18 另验）",
    }
    write_json(out_dir / "iteration.json", result)
    write_json(out_dir / "av-archive.json", archive)
    ledger.save()
    return result


# ---------------------------------------------------------------------------
# 9.4 confirm / resume：确认预算门与身份核验恢复
# ---------------------------------------------------------------------------


def run_av_confirm(out_dir: Path, archive_path: Path, epoch_path: Path, *,
                   confirm_budget: Optional[float] = None,
                   confirm_authorization: Optional[Mapping[str, Any]] = None,
                   extra_evaluations: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """confirm-action-value：C2 nominate + 确认预算门（无确认额度即拒并说明）。"""

    out_dir = guard_out_dir(Path(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    authorized_budget = 0.0
    if isinstance(confirm_authorization, Mapping):
        if confirm_authorization.get("authorized") is True:
            authorized_budget = float(confirm_authorization.get("confirm_budget") or 0.0)
    ledger = ActionValueLedger(out_dir / "av-ledger.json",
                               confirm_authorized_budget=authorized_budget)
    if authorized_budget <= 0:
        result = {
            "schema": "sitin-action-value-confirm/1", "ok": False,
            "refused": ("无确认额度：确认预算默认 {0} 且硬禁继承现状（不从开发额度划拨）。"
                        "需要独立确认时须显式授权文件（confirm_budget>0 且 "
                        "authorized=true），并以新版账本与入口解除，不能只改配置数字").format(
                            AV_CONFIRM_DEFAULT_BUDGET),
            "confirm_policy": "confirm 硬禁（SearchLedger.reserve 同一纪律继承）",
        }
        write_json(out_dir / "confirm.json", result)
        return result
    archive_mod = av_archive()
    archive = json.loads(Path(archive_path).read_text(encoding="utf-8"))
    epoch = json.loads(Path(epoch_path).read_text(encoding="utf-8"))
    try:
        reservation = ledger.reserve(step_id="confirm:nominate",
                                     account="confirm_reserved",
                                     amount=min(authorized_budget, 1.0),
                                     note="提名补齐预算预留（独立确认账）")
    except TaskAlreadySettled as error:
        # S3：已结算任务不得原地再次预留——重复调用确认入口返回可读拒绝，不崩栈、不双计。
        result = {"schema": "sitin-action-value-confirm/1", "ok": False,
                  "refused": ("本运行目录的确认提名已结算，不得原地再次预留（S3）："
                              "如需重新提名请换新目录，或按恢复对账显式让位；{0}".format(
                                  error))}
        write_json(out_dir / "confirm.json", result)
        return result
    try:
        nomination = archive_mod.nominate_candidate(
            archive, epoch, budget=confirm_budget, extra_evaluations=extra_evaluations)
    finally:
        ledger.settle(reservation, actual=0.0, note="nominate 完成（补齐成本另计）")
    result = {"schema": "sitin-action-value-confirm/1", "ok": True,
              "nomination": nomination,
              "confirm_authorized_budget": authorized_budget,
              "confirmation_executor": "pending",
              "note": ("本入口当前只完成**提名**；独立确认执行器（R7：独立自然根执行"
                       "与预声明下界检验）落码前不冒充确认结果——nomination 是提名"
                       "材料，不是一次性确认结论（Q5 诚实化）")}
    write_json(out_dir / "confirm.json", result)
    ledger.save()
    return result


def av_resume_identity_matches(record: Mapping[str, Any], identity: Mapping[str, Any]) -> Tuple[bool, str]:
    """resume 身份核验：run_id + candidate_id/evaluation_id/panel_epoch/合同 sha256
    逐项匹配；任何身份不符拒绝续写（§6.3 恢复纪律）。"""

    if not isinstance(record, Mapping):
        return False, "无在案运行记录"
    stored = record.get("identity") or {}
    for key in ("candidate_id", "evaluation_id", "panel_epoch", "contract_sha256"):
        if key not in identity:
            return False, "身份材料缺字段 {0}".format(key)
        if str(stored.get(key)) != str(identity[key]):
            return False, ("身份字段 {0} 不符（在案 {1}，本次 {2}）："
                           "工具/依赖/面板变化使旧结果失效，拒绝续写").format(
                               key, str(stored.get(key))[:16], str(identity[key])[:16])
    return True, ""


def run_av_resume(out_dir: Path, *, run_id: str,
                  identity: Mapping[str, Any]) -> Dict[str, Any]:
    """resume：核验完整身份后恢复；任何身份不符拒绝续写。"""

    out_dir = Path(out_dir)
    iteration_path = out_dir / "iteration.json"
    if not iteration_path.is_file():
        result = {"schema": "sitin-action-value-resume/1", "ok": False,
                  "refused": "运行目录没有 iteration.json：没有可恢复的在案迭代"}
        write_json(out_dir / "resume.json", result)
        return result
    record = json.loads(iteration_path.read_text(encoding="utf-8"))
    if record.get("run_id") != run_id:
        result = {"schema": "sitin-action-value-resume/1", "ok": False,
                  "refused": "run_id 不符（在案 {0}，本次 {1}）：拒绝续写".format(
                      record.get("run_id"), run_id)}
        write_json(out_dir / "resume.json", result)
        return result
    matched, reason = av_resume_identity_matches(record, identity)
    if not matched:
        result = {"schema": "sitin-action-value-resume/1", "ok": False,
                  "refused": "身份核验失败：{0}".format(reason)}
        write_json(out_dir / "resume.json", result)
        return result
    result = {
        "schema": "sitin-action-value-resume/1", "ok": True,
        "run_id": run_id,
        "resumed_steps": [item.get("step") for item in record.get("steps", [])],
        "identity": record.get("identity"),
        "note": "身份逐项核验通过；续写沿 §9.4 顺序从下一未完成步继续",
    }
    write_json(out_dir / "resume.json", result)
    return result


# ============================================================ 9.4b 进化编排状态机
#
# R5（REVIEW-V4 Q5 修复）：evolve/resume 升级为真实编排。每步持久化
# state.json（tmp+rename 原子写），下一步由落盘状态决定；生成步接 delegate
# 文件式通道（产 pending 交接件后停下等外部回复，恢复时从已存在回复继续
# 解析，不免费重发）；评价步接 R3 run_av_evaluation 与 R4 natural_panel
# （强制共享账本）；档案步接 R4 update_archive/apply_challenge(persist_dir)
# 持久档案，不再每次重建单候选档案。旧 run_av_iteration 保留为显式 mock
# 演示（测试用）；生产入口 = 本节状态机（--generation-mock 为显式测试模式）。
# 状态名与五事务边界按 CONTINUOUS-EVOLUTION-PLAN §5/§7。
# ============================================================

#: 迭代状态文件 schema（每步原子落盘：state.json）。
AV_ITERATION_STATE_SCHEMA = "sitin-action-value-iteration-state/1"
#: 批次报告 schema（§11：完成状态/停止原因/剩余额度/证据引用/唯一下一步）。
AV_BATCH_REPORT_SCHEMA = "sitin-action-value-batch-report/1"
#: §5 步骤状态机主序（REFRESH_PENDING 可回 ARCHIVE_COMMITTED，另有终态）。
AV_STATE_ORDER = (
    "RESERVED", "GENERATED", "ADMITTED", "BEHAVIOR_CHECKED",
    "CONDITIONAL_EVALUATED", "NATURAL_EVALUATED", "SUMMARIZED",
    "REFRESH_PENDING", "ARCHIVE_COMMITTED", "ITERATION_COMPLETE",
)
#: 明确终态（REJECTED/INPUT_GAP/BUDGET_EXHAUSTED/EXECUTION_FAILED）。
AV_TERMINAL_STATES = ("REJECTED", "INPUT_GAP", "BUDGET_EXHAUSTED",
                      "EXECUTION_FAILED")
#: 五事务边界的落盘文件名（迭代目录 transactions/ 下）。
AV_TX_FILES = {
    "model_call_before": "tx-model-call-before.json",
    "generation_complete": "tx-generation-complete.json",
    "eval_conditional_begin": "tx-eval-conditional-begin.json",
    "eval_conditional_complete": "tx-eval-conditional-complete.json",
    "eval_natural_begin": "tx-eval-natural-begin.json",
    "eval_natural_complete": "tx-eval-natural-complete.json",
    "channel_refresh": "tx-channel-refresh.json",
    # P7b：补根事务件（pending_partial → 补根 → 重试提交 的完整路径可核）。
    "refresh_fill": "tx-refresh-fill.json",
    # P7c：家族通道事务件（声明/补根 → 家族重组 → 家族席与家族 epoch 结局）。
    "family_refresh": "tx-family-refresh.json",
    "batch_end": "tx-batch-end.json",
}


def av_atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """原子写 JSON：同目录 tmp 文件 + os.replace（崩溃不留半写主文件）。"""

    av_atomic_write_bytes(
        Path(path),
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def av_state_save(state_path: Path, state: Mapping[str, Any]) -> None:
    data = dict(state)
    data["updated_at_utc"] = utc_now()
    av_atomic_write_json(state_path, data)


def av_state_load(state_path: Path) -> Dict[str, Any]:
    return json.loads(Path(state_path).read_text(encoding="utf-8"))


def av_state_history_append(state: Dict[str, Any], status: str,
                            note: str = "", **fields: Any) -> None:
    """状态历史只追加不改写（每步一条；恢复后可核对哪些步执行过几遍）。"""

    state.setdefault("step_history", []).append({
        "status": status, "note": note, "at_utc": utc_now(),
        "fields": {key: value for key, value in fields.items() if value is not None},
    })
    state["status"] = status


def _av_tx_write(iter_dir: Path, tx_key: str, payload: Mapping[str, Any]) -> Path:
    path = Path(iter_dir) / "transactions" / AV_TX_FILES[tx_key]
    av_atomic_write_json(path, payload)
    return path


def av_state_identity_matches(state: Mapping[str, Any],
                              identity: Mapping[str, Any]) -> Tuple[bool, str]:
    """状态机 resume 身份核验：提供的每个身份字段必须与在案一致（Q5/§5）。"""

    stored = state.get("identity") or {}
    for key, value in identity.items():
        if key not in stored:
            return False, "在案身份缺字段 {0}".format(key)
        if str(stored[key]) != str(value):
            return False, ("身份字段 {0} 不符（在案 {1}，本次 {2}）："
                           "依赖/面板变化使旧状态失效，拒绝续写").format(
                               key, str(stored[key])[:16], str(value)[:16])
    return True, ""


def _av_reserve_generation_tokens(ledger: "ActionValueLedger", *, iteration_no: int,
                                  tokens_input: float, tokens_output: float
                                  ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """原子预留本次生成的输入/输出 token；额度不够时不留下半笔预留。"""
    requests = (
        ("tokens_input", float(tokens_input), "生成调用 token 输入上界预留（delegate 文件通道；回复 usage 未知时保守计费）"),
        ("tokens_output", float(tokens_output), "生成调用 token 输出上界预留（含一次解析修复）"),
    )
    with ledger._exclusive():
        for account, amount, _note in requests:
            total = ledger.authorized_total(account)
            if total is None:
                raise LedgerUnauthorized(
                    "账户 {0} 未声明授权额度（生成预留）：正数预留 fail-closed".format(account))
            remaining = ledger.remaining(account)
            if remaining is None or amount > remaining + 1e-9:
                raise LedgerOverAuthorized(
                    "生成预留被拒：账户 {0} 的可用余额 {1} 不足以预留 {2}"
                    .format(account, remaining, amount))
        rows = []
        previous = list(ledger.reservations)
        try:
            for account, amount, note in requests:
                rows.append(ledger._reserve_locked(
                    step_id="iter{0}:gen-tokens-{1}".format(
                        iteration_no, "in" if account == "tokens_input" else "out"),
                    account=account, amount=amount, note=note, usage_unknown=False, persist=False))
            # 两笔经同一锁校验，只做一次原子文件替换；崩溃时旧账或完整新账二选一。
            ledger.save()
        except BaseException:
            ledger.reservations = previous
            raise
    return rows[0], rows[1]


def _av_ledger_for_run(run_root: Path, authorization: Optional[Mapping[str, Any]],
                       state: Optional[Mapping[str, Any]] = None) -> "ActionValueLedger":
    """迭代共享账本（run_root/av-ledger.json；授权额度从令牌读，Q3）。"""

    return ActionValueLedger.load(
        Path(run_root) / "av-ledger.json",
        authorized_budgets=av_ledger_budgets_from_authorization(authorization))


def av_start_iteration(run_root: Path, *, operator: str = "i1",
                       predicate: str = "branch_open", opponent: str = "H",
                       generation_mode: str = "delegate",
                       seed_name: str = "efficiency_seed",
                       natural_roots: int = 1, natural_seats: int = 1,
                       prefix_source: str = "scripted_fixture",
                       panel_seed: int = 20260916,
                       parent_dir: Optional[Path] = None,
                       authorization: Optional[Mapping[str, Any]] = None,
                       reply_envelope: Optional[Path] = None,
                       archive_in: Optional[Mapping[str, Any]] = None,
                       family_channel: Optional[str] = None,
                       family_refresh: Optional[Sequence[Mapping[str, Any]]] = None,
                       declaration_probe: Optional[
                           Callable[..., Mapping[str, Any]]] = None,
                       test_runtime_factory: Optional[
                           Callable[[], Mapping[str, Any]]] = None,
                       ) -> Dict[str, Any]:
    """开一个新迭代：预留上界（§7 步 1）→ 落 RESERVED 状态并返回。

    family_channel / family_refresh（P7c）：**家族通道按显式声明启用**——
    family_channel 给出本迭代接线的家族通道（族名或该族子场景谓词），
    family_refresh 给出本迭代声明的家族刷新批（每条为显式根声明：
    子场景 × 对手情景 × 面板种子 × 根序号）。两者缺省即不接线（零家族评价、
    既有 normal 通道路由与账目逐字不变）。

    批次身份在此时冻结（合同/执行器/面板配置）；candidate_id/evaluation_id
    在对应步完成时补入 identity（§5：恢复核验逐项匹配）。`archive_in` 是本次
    调度所用的**共享档案**（路径/来源/条目与席位计数/提案号），原样落进
    state.plan 供事后核对"计划是以哪一份档案生成的"。
    """

    # 作者调用预留之前验证真实面板；所有 new/next 入口均从同一授权声明接线。
    if _sibling("sitin_execution_profile").from_authorization(authorization)["research_only"]:
        raise ValueError("研究额度须使用受监督的准入/条件/自然评测入口；自动档案循环尚未接线，禁止预留作者费用")
    development_behavior_panel = av_development_behavior_panel(
        (authorization or {}).get("development_behavior_panel"))
    supervisor_feedback = (authorization or {}).get("supervisor_feedback")
    if supervisor_feedback is not None and (not isinstance(supervisor_feedback, str)
                                           or len(supervisor_feedback) > 12000):
        raise ValueError("supervisor_feedback 必须是至多12000字符的监督备注")
    author_feedback_mode = av_feedback().author_feedback_mode(
        (authorization or {}).get("author_feedback_mode"))
    run_root = guard_out_dir(Path(run_root))
    run_root.mkdir(parents=True, exist_ok=True)
    gates = av_gates()
    gen = av_generate()
    if generation_mode not in ("delegate", "mock"):
        raise ValueError("generation_mode 必须是 delegate/mock，得到 {0!r}".format(
            generation_mode))
    ledger = _av_ledger_for_run(run_root, authorization)
    existing = sorted((run_root / "iterations").glob("iter-*")) if (
        run_root / "iterations").is_dir() else []
    iteration_no = len(existing) + 1
    iter_dir = run_root / "iterations" / "iter-{0:02d}".format(iteration_no)
    iter_dir.mkdir(parents=True, exist_ok=True)
    contract_sha = gates.av_contract()[1]
    run_id = sha256_text(canonical_json({
        "iteration_no": iteration_no, "operator": operator,
        "predicate": predicate, "opponent": opponent, "panel_seed": panel_seed,
        "contract_sha256": contract_sha, "generation_mode": generation_mode,
    }))[:24]
    # —— S2：开轮冻结**可重算清单**（十面）并落进身份；计划块与清单同源，
    #    恢复时用同一份 plan 重算，避免"开轮无候选/恢复有候选"互相矛盾。
    plan_block: Dict[str, Any] = {
        "operator": operator, "predicate": predicate, "opponent": opponent,
        "panel_seed": panel_seed, "prefix_source": prefix_source,
        "natural_roots": int(natural_roots),
        "natural_seats": int(natural_seats),
        "natural_opponents": ["H", "M"],
        "generation_mode": generation_mode,
        "parent_dir": str(parent_dir) if parent_dir else None,
        "seed_name": seed_name,
        # 本迭代的调度输入档案（跨迭代档案链；见 av_discover_archive）。
        # 未接线的旧调用路径显式记 unspecified，不留 None 冒充"已接线"。
        "archive_in": (dict(archive_in) if isinstance(archive_in, Mapping)
                       else {"source": "unspecified", "path": None,
                             "note": "调用方未提供调度输入档案"}),
        # P7c：家族通道接线声明（缺省 None/[] = 不接线，零家族评价、零行为变化）。
        "family_channel": (str(family_channel) if family_channel else None),
        "family_refresh": [dict(row) for row in (family_refresh or ())
                           if isinstance(row, Mapping)],
        "development_behavior_panel": development_behavior_panel,
        "supervisor_feedback": supervisor_feedback,
        "author_feedback_mode": author_feedback_mode,
    }
    frozen_manifest = av_frozen_manifest(plan=plan_block)
    state: Dict[str, Any] = {
        "schema": AV_ITERATION_STATE_SCHEMA,
        "run_id": run_id,
        "iteration_no": iteration_no,
        "created_at_utc": utc_now(),
        "status": "RESERVED",
        "step_history": [],
        "identity": {
            "run_id": run_id,
            "contract_sha256": contract_sha,
            "target_contract_sha256": sha256_file(
                _project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
                "/contracts/group-dev-v1.json")),
            "executor_version": gates._av_module(
                "hangma_bot.policy.action_value_executor").EXECUTOR_VERSION,
            "deps_digest": gates._av_module(
                "hangma_bot.policy.action_value_executor").compute_deps_digest(),
            "frozen_manifest": frozen_manifest,
            "frozen_manifest_digest": av_frozen_manifest_digest(frozen_manifest),
            "predicate": predicate, "opponent": opponent,
            "panel_seed": panel_seed, "generation_mode": generation_mode,
        },
        "plan": plan_block,
        "generation": {"mode": generation_mode,
                       "reply_envelope": str(reply_envelope) if reply_envelope else None,
                       "phase": None},
        "iter_dir": str(iter_dir),
    }
    # —— §7 步 1：预留上界。**只预留生成侧 token**（生成步在本机执行，无其他
    # 记账方）；条件前缀与自然桌赛由各自步骤经共享账本自行"先预留后执行"
    # （run_av_evaluation / run_natural_panel 已内置），此处不代记以免双计。
    call_limits = av_generation_call_limits_from_authorization(authorization)
    if call_limits is None:
        # 兼容旧令牌：沿用既有固定上界与按账户额度缩小的行为。
        budgets = av_ledger_budgets_from_authorization(authorization) or {}
        tokens_in = min(2048.0, float(budgets.get("tokens_input", 2048.0)))
        tokens_out = min(8192.0, float(budgets.get("tokens_output", 8192.0)))
    else:
        # 显式调用上界是作者实际交付容量，不能被账户总额度静默缩小；余额不足必须拒绝。
        tokens_in = call_limits["tokens_input"]
        tokens_out = call_limits["tokens_output"]
    _av_reserve_generation_tokens(ledger, iteration_no=iteration_no,
                                  tokens_input=tokens_in, tokens_output=tokens_out)
    state["reservations"] = {
        "tokens_input": tokens_in, "tokens_output": tokens_out,
        # 以下为计划量（由对应步骤的共享账本预留，不在此重复记账）：
        "prefix_generation_planned": 1.0,
        "tables_full_planned": float(int(natural_roots) * int(natural_seats) * 2 * 2 * 2),
    }
    av_state_history_append(state, "RESERVED", "批次身份冻结并预留上界")
    # —— P9 FAMCOST：家族声明**解析**（声明必须由"可物化"的根构成）——
    # 只在真实前缀路由 + 有家族声明时接线；夹具/未声明路径零行为变化（旧调用方
    # 逐字不变）。探针经同一共享账本先预留后结算；预算门不足即停止并具名留痕。
    # —— S4：未启用家族**在这里就跳过**（不解析声明、不花探针、不建 epoch）——
    declared_family = _av_family_declared_channel(state)
    if declared_family is not None and declared_family not in AV_FAMILY_ENABLED_FAMILIES:
        scope = av_family_scope(declared_family)
        state["family_scope"] = scope
        state["family_refresh_resolved"] = {
            "schema": AV_FAMILY_DECLARATION_SCHEMA,
            "channel": plan_block["family_channel"],
            "request": list(plan_block["family_refresh"]),
            "resolved": [], "trace": [], "complete": False,
            "stop_reason": AV_FAMILY_INACTIVE_STOP_REASON,
            "scope": scope,
            "note": ("S4：本版只启用 {0}；{1} 显式 inactive，调度跳过——不产生该族任何"
                     "样本或 epoch，也**不把它当作 0**（None 不得当 0）").format(
                         list(AV_FAMILY_ENABLED_FAMILIES), declared_family),
        }
    if (str(prefix_source) == "v2_behavior" and plan_block["family_channel"]
            and plan_block["family_refresh"]
            and _av_family_declared_channel(state) in AV_FAMILY_ENABLED_FAMILIES):
        try:
            av_resolve_family_declarations(
                state, run_root, ledger=ledger,
                probe=declaration_probe, test_runtime_factory=test_runtime_factory)
        except AV_LEDGER_FAILURE_ERRORS as error:
            state["family_refresh_resolved"] = {
                "schema": AV_FAMILY_DECLARATION_SCHEMA,
                "channel": plan_block["family_channel"],
                "request": list(plan_block["family_refresh"]), "resolved": [],
                "trace": [], "complete": False,
                "stop_reason": "ledger_rejected:{0}".format(type(error).__name__),
                "note": "声明解析被账本拒绝（预算/授权）：不物化任何根、保原席原 epoch"}
    # —— 跨目录连续恢复：开轮**固化调度输入的内容身份**（档案 / 家族 epoch /
    #    根用途清单 + 固定快照）；此后读取走快照，跨目录登记项在恢复前核对内容 ——
    try:
        av_archive_input_freeze(state, run_root)
    except (ArchiveInputFreezeFailed, OSError) as error:
        # P16-S1：必需输入冻结失败 ⇒ **开轮即具名停止**（ok=False 才是真的失败；
        # 旧实现写 ok=True + status=freeze_failed，之后核验又因"缺身份"返回
        # unregistered/ok=True，保护形同虚设）。状态落盘后由推进入口拒绝继续。
        problems = [{
            "kind": "archive_input_freeze",
            "reason": "必需输入无法冻结：{0}（{1}）".format(
                error, AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON)}]
        state["archive_input"] = {
            "schema": AV_ARCHIVE_INPUT_IDENTITY_SCHEMA, "ok": False,
            "status": "freeze_failed",
            "stop_reason": AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON,
            "problems": problems,
            "checked_at_utc": utc_now(),
            "note": ("输入内容身份冻结失败：**不得执行、不得提交**——修复输入后显式"
                     "新开评价（不自愈、不静默降级）")}
        state["stop_reason"] = AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON
        av_state_save(iter_dir / "state.json", state)
        return state
    av_state_save(iter_dir / "state.json", state)
    return state


class AvFeedbackRefused(RuntimeError):
    """M1 的父代反馈不可执行（误绑定 / 缺读数 / 确认数据混入）：**不发任务**。"""


#: M1 读取闸门认得的反馈结构版本（与 sitin_feedback.PROJECTION_SCHEMA 同值）。
#: 消费端**按版本核对**而不是"字段看起来像就收"：R9/P5（复审 R8 §6 F2）。
AV_FEEDBACK_SCHEMA = "sitin-feedback-projection/1"

#: 准入身份块里**纯说明性**的键（不参与逐项核对）。
AV_ADMISSION_DESCRIPTIVE_KEYS = ("candidate_id_inputs", "deps_digest_basis")

def _av_feedback_evidence_drift(payload: Mapping[str, Any],
                                feedback_path: Path) -> List[str]:
    """按**当前盘上字节**重算父代反馈的来源摘要（不信产物自报）。

    反馈只登记"读过的产物 + 逐文件字节摘要 + 合成摘要"；这里逐条重算：文件缺失、
    字节变了、或合成摘要对不上，都说明反馈写的不是现在这份产物——不得据此发任务。
    """

    identity = payload.get("identity") or {}
    evidence = identity.get("evidence") if isinstance(identity, Mapping) else None
    if not isinstance(evidence, Mapping) or not evidence.get("files"):
        return ["反馈未登记来源摘要（identity.evidence.files）：拒绝按布尔声明放行"]
    base = Path(feedback_path).parent.parent
    problems: List[str] = []
    current: List[Dict[str, Any]] = []
    for entry in evidence.get("files") or []:
        if not isinstance(entry, Mapping):
            problems.append("来源摘要条目不是映射：{0!r}".format(entry))
            continue
        rel = entry.get("rel")
        target = (base / str(rel)) if rel else Path(str(entry.get("path") or ""))
        if not target.is_file():
            problems.append("来源摘要登记的文件已不在：{0}".format(rel or target))
            continue
        actual = sha256_file(target)
        if actual != str(entry.get("sha256") or ""):
            problems.append("来源摘要与当前字节不一致：{0}".format(rel or target))
            continue
        current.append({"kind": entry.get("kind"), "rel": rel, "sha256": actual})
    recorded_digest = str(evidence.get("digest") or "")
    if not problems:
        current.sort(key=lambda item: (str(item["rel"]), str(item["kind"])))
        recomputed = sha256_text(json.dumps(current, ensure_ascii=False, sort_keys=True))
        if recomputed != recorded_digest:
            problems.append("来源摘要合成摘要与当前产物清单不一致")
    return problems


def _av_feedback_admission_checks(payload: Mapping[str, Any],
                                  parent_source: Optional[str]
                                  ) -> List[str]:
    """按**当前准入身份构造器**逐项核对反馈登记的准入身份。

    P4/M1 起准入身份含评价材料与评判语义字段（`materials_sha256` /
    `executor_version` / `thresholds`）。这里不硬编码字段清单，而是拿
    `gates.av_identity_binding(父代源码)` 的当前键集合逐项比对：构造器加了新身份
    字段，闸门**自动**要求反馈也带上它——因此不能只信 executable/refusals 两个布尔。
    """

    identity = payload.get("identity") or {}
    recorded = identity.get("admission") if isinstance(identity, Mapping) else None
    if parent_source is None:
        return []
    try:
        expect = av_gates().av_identity_binding(parent_source)
    except Exception as error:  # noqa: BLE001 - 构造器不可用即不可核对
        return ["准入身份不可重算（{0}: {1}）：拒绝放行".format(
            type(error).__name__, error)]
    if not isinstance(recorded, Mapping):
        return ["反馈未登记准入身份（identity.admission）：拒绝按布尔声明放行"]
    problems: List[str] = []
    for key in sorted(expect):
        if key in AV_ADMISSION_DESCRIPTIVE_KEYS:
            continue
        if key not in recorded:
            problems.append("准入身份缺字段 {0}（当前构造器要求它参与身份）".format(key))
        elif recorded.get(key) != expect[key]:
            problems.append("准入身份字段 {0} 不符（反馈 {1}，当前 {2}）".format(
                key, str(recorded.get(key))[:24], str(expect[key])[:24]))
    return problems


def _av_m1_feedback(state: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """读取 M1 父代的三段反馈投影并判定可执行性（R7/P9，R9/P5 加身份绑定）。

    返回 `(payload, verdict)`。拒绝条件（全部 fail-closed）：

    - 找不到父代 `summary/feedback.json` / 不可解析 → 不可执行（M1 的合同要求附
      父代三段反馈，缺反馈即缺读数，不拿占位文本顶替）；
    - 投影 `executable` 不为真 → 不可执行，带回拒绝码与**拒绝证据文件路径**；
    - **结构版本**不是 `AV_FEEDBACK_SCHEMA` → 不可执行（旧结构的字段语义未核）；
    - **实际父代身份**：从父代产物重算 `candidate_id`/`code_sha256`，与反馈登记的
      `identity.candidate_id`/`source_sha256`/`source_file_sha256` 逐项比对；
      与 `plan.parent_candidate_id` 也要一致（不一致即"旧父代反馈"，复审 R8 §6 F2）；
    - **来源摘要**：逐文件按当前字节重算（反馈写完之后产物被改写/替换即拒绝）；
    - **准入身份**：按当前准入身份构造器逐项核对（含评价材料与评判语义字段）。

    只有全部相符且 `executable=true` 才允许渲染提示词。
    """

    plan = state.get("plan") or {}
    parent_dir = plan.get("parent_dir")
    if not parent_dir:
        return {}, {"ok": False, "codes": ["input.parent_missing"],
                    "detail": "M1 必须有父代目录（plan.parent_dir）", "path": None}
    feedback_path = Path(parent_dir).parent / "summary" / "feedback.json"
    if not feedback_path.is_file():
        return {}, {"ok": False, "codes": ["input.feedback_missing"],
                    "detail": "父代没有 summary/feedback.json：M1 缺可修订证据，"
                              "拒绝生成任务",
                    "path": str(feedback_path)}
    try:
        payload = json.loads(feedback_path.read_text(encoding="utf-8"))
    except ValueError as error:
        return {}, {"ok": False, "codes": ["input.feedback_unreadable"],
                    "detail": "父代反馈不可解析：{0}".format(error),
                    "path": str(feedback_path)}
    refusals = list(payload.get("refusals") or [])
    executable = bool(payload.get("executable")) and not refusals
    problems: List[Tuple[str, str]] = []
    if payload.get("schema") != AV_FEEDBACK_SCHEMA:
        problems.append(("input.feedback_schema", "反馈结构版本 {0!r} 不是 {1}".format(
            payload.get("schema"), AV_FEEDBACK_SCHEMA)))
    identity = payload.get("identity")
    if not isinstance(identity, Mapping):
        problems.append(("input.feedback_schema", "反馈缺 identity 块"))
        identity = {}
    # —— 实际父代身份（按父代产物重算，不信命令行也不信反馈自报）——
    binding = None
    try:
        binding = av_generate().av_parent_binding(Path(parent_dir))
    except Exception as error:  # noqa: BLE001 - 父代产物不可核验即不可放行
        problems.append(("input.parent_unreadable",
                         "父代产物不可核验（{0}: {1}）".format(
                             type(error).__name__, str(error)[:120])))
    plan_parent = plan.get("parent_candidate_id")
    if identity.get("candidate_id") != (binding["candidate_id"] if binding
                                        else plan_parent):
        problems.append(("identity.feedback_parent_mismatch",
                         "反馈是给候选 {0} 的，本次 M1 的父代是 {1}".format(
                             str(identity.get("candidate_id"))[:16],
                             str((binding or {}).get("candidate_id")
                                 or plan_parent)[:16])))
    if binding is not None and plan_parent and \
            str(plan_parent) != str(binding["candidate_id"]):
        problems.append(("identity.feedback_parent_mismatch",
                         "计划父代 {0} 与父代产物 {1} 不一致".format(
                             str(plan_parent)[:16], str(binding["candidate_id"])[:16])))
    if binding is not None:
        if identity.get("source_file_sha256") != binding["code_sha256"]:
            problems.append(("identity.feedback_source_mismatch",
                             "来源摘要（文件字节）{0} 与父代源码 {1} 不符".format(
                                 str(identity.get("source_file_sha256"))[:16],
                                 str(binding["code_sha256"])[:16])))
        elif sha256_text(binding["code"]) != str(identity.get("source_sha256") or ""):
            problems.append(("identity.feedback_source_mismatch",
                             "来源摘要（源码文本）与父代源码内容不符"))
    for detail in _av_feedback_evidence_drift(payload, feedback_path):
        problems.append(("identity.feedback_evidence_drift", detail))
    for detail in _av_feedback_admission_checks(
            payload, binding["code"] if binding is not None else None):
        problems.append(("identity.feedback_admission_mismatch", detail))
    # 诊断要完整：身份问题与投影拒绝码一并报出（不互相遮蔽）。
    codes = sorted({code for code, _detail in problems}
                   | {str(item.get("code")) for item in refusals})
    if not codes and not executable:
        codes = ["input.feedback_not_executable"]
    details = ["{0}={1}".format(code, detail) for code, detail in problems] or [
        "{0}={1}".format(item.get("code"), item.get("detail")) for item in refusals]
    ok = executable and not problems
    return payload, {
        "ok": ok,
        "codes": sorted(set(codes)),
        "detail": "；".join(details) or (
            "" if ok else "反馈未声明 executable=true"),
        "path": str(feedback_path),
        "schema": payload.get("schema"),
        "status": payload.get("status"),
        "parent_candidate_id": (binding or {}).get("candidate_id") or plan_parent,
    }


def _av_render_feedback_payload(feedback: Mapping[str, Any], *,
                                mode: Any = None) -> Dict[str, str]:
    """把反馈投影渲染成提示词三段文本（逐条列出，条目与产物逐项对账）。"""

    segments = av_feedback().author_projection_segments(feedback, mode=mode)
    return {
        "facts": segments.get("facts", ""),
        "associated_results": segments.get("associated_results", ""),
        "mechanism_hypothesis": segments.get("mechanism_hypothesis", ""),
        "schema": str(feedback.get("schema") or ""),
        "status": str(feedback.get("status") or ""),
    }


def _av_generation_packet(state: Mapping[str, Any], gen: Any,
                          run_root: Path) -> Any:
    """按状态机构造 TaskContract 与提示词（与 sitin_generate 同一渲染）。"""

    plan = state["plan"]
    parent = None
    feedback_payload = None
    if plan["operator"] == "m1":
        if not plan.get("parent_dir"):
            raise ValueError("M1 必须有父代目录（plan.parent_dir）")
        bound = gen.av_parent_binding(Path(plan["parent_dir"]))
        parent = {"identity": bound["identity"],
                  "candidate_id": bound["candidate_id"],
                  "prompt_sha256": bound["prompt_sha256"],
                  "attempt_dir": bound["dir"],
                  "code_sha256": bound["code_sha256"],
                  "thought": bound.get("thought") or "",
                  "code": bound["code"], "load_ok": bound.get("load_ok")}
        payload, verdict = _av_m1_feedback(state)
        if not verdict["ok"]:
            raise AvFeedbackRefused(verdict["detail"] or "父代反馈不可执行")
        feedback_payload = _av_render_feedback_payload(
            payload, mode=plan.get("author_feedback_mode"))
    objective = gen.default_objective_summary()
    if plan.get("supervisor_feedback"):
        objective += ("\n\n监督开发备注（人工研发假设与历史观察；不替代规则或机器合同，"
                      "不是模型自测或当前效果证据）：\n" + plan["supervisor_feedback"])
    payload = gen.render_action_value_task_contract(
        objective_summary=objective,
        panel_boundary="开发面板：条件机会（{0}/{1}）+ 正常阶段（group-dev-v1）".format(
            plan["predicate"], plan["opponent"]),
        prompt_role=("{0}（编排状态机；delegate 文件式通道）".format(
            plan["operator"].upper())),
        parent=parent, feedback=feedback_payload,
        budget_note="预算以授权令牌与共享账本为准；失败与重试同样计费")
    return gen.build_action_value_prompt(plan["operator"], payload)


def _av_restore_committed_generation(state: Dict[str, Any], iter_dir: Path,
                                     generation: Dict[str, Any]) -> bool:
    """S3：生成事务已提交、状态未提交时按**已提交产物**重建状态。

    判据（全部满足才算"已提交"，否则走正常摄入）：检查点 completed + candidate.py 与
    检查点记录的源码摘要一致 + 调用后事务件存在。重建不重复摄入、不重复计费、
    不重发提示词。
    """

    checkpoint = av_checkpoint_load(iter_dir, AV_GENERATION_CHECKPOINT)
    if not checkpoint or str(checkpoint.get("status")) != "completed":
        return False
    attempt_dir = Path(checkpoint.get("attempt_dir") or (iter_dir / "generation"))
    candidate_path = attempt_dir / "candidate.py"
    if not candidate_path.is_file():
        return False
    code_text = candidate_path.read_text(encoding="utf-8")
    if sha256_text(code_text) != str(checkpoint.get("candidate_source_sha256")):
        return False
    if not (iter_dir / "transactions" / AV_TX_FILES["generation_complete"]).is_file():
        return False
    state["candidate_source"] = code_text
    state["identity"]["candidate_id"] = checkpoint.get("candidate_id")
    state["identity"]["candidate_source_sha256"] = checkpoint.get(
        "candidate_source_sha256")
    generation.update({"phase": "ingested",
                       "candidate_id": checkpoint.get("candidate_id"),
                       "attempt_dir": str(attempt_dir),
                       "restored_from_checkpoint": True})
    av_state_history_append(
        state, "GENERATED",
        "恢复：生成事务已提交，按已提交产物重建状态（不重复摄入、不重复计费）",
        candidate_id=checkpoint.get("candidate_id"))
    return True


def _step_generate(state: Dict[str, Any], run_root: Path, ledger: "ActionValueLedger",
                   stop_after: Optional[str]) -> Dict[str, Any]:
    """RESERVED→GENERATED：delegate 产 pending 交接件并停下等回复；或 mock。

    事务边界：模型调用前（tx-model-call-before）在 emit 时写；生成完成
    （tx-generation-complete：原始回复+usage 或 unknown+解析产物）在摄入后写。
    恢复规则：phase=prompt_emitted 时**不重发**，只在回复文件出现后继续解析。
    """

    gen = av_generate()
    gates = av_gates()
    iter_dir = Path(state["iter_dir"])
    generation = state.setdefault("generation", {})
    # —— S3 恢复对账：回复已摄入、状态未提交（检查点/事务件已落盘）——
    if generation.get("phase") == "prompt_emitted":
        if _av_restore_committed_generation(state, iter_dir, generation):
            return {"advanced": "GENERATED", "restored": True}
    # —— A5：M1 的父代反馈必须先过可执行性判定；不通过即**不发提示词、不计费**，
    #    整轮记 INPUT_GAP 终态（误绑定 / 缺读数 / 确认数据混入三种情形都在此拦住）。
    if state["plan"]["operator"] == "m1" and generation.get("phase") != "prompt_emitted":
        _payload, verdict = _av_m1_feedback(state)
        if not verdict["ok"]:
            state["feedback_refusal"] = verdict
            state.setdefault("input_gaps", []).append(
                "m1_feedback_refused：{0}".format(verdict["detail"] or verdict["codes"]))
            state["stop_reason"] = "m1_feedback_refused"
            av_state_history_append(
                state, "INPUT_GAP",
                "M1 父代反馈不可执行：拒绝生成任务（不发提示词、不计费）",
                codes=verdict["codes"], feedback_path=verdict.get("path"))
            return {"terminal": "INPUT_GAP"}
    if generation.get("phase") != "prompt_emitted":
        try:
            packet = _av_generation_packet(state, gen, run_root)
        except av_feedback().FeedbackInputError as error:
            # 摘要不能对账时不发另一种提示，也不把输入缺陷算成模型失败。
            handoff_exists = (
                (iter_dir / "transactions" / "tx-model-call-before.json").exists()
                or (iter_dir / "pending" / state["plan"]["operator"] / "prompt.txt").exists()
                or (iter_dir / "reply-envelope.json").exists())
            if not handoff_exists:
                step_ids = {"iter{0}:gen-tokens-in".format(state["iteration_no"]),
                            "iter{0}:gen-tokens-out".format(state["iteration_no"])}
                for reservation in list(ledger.reservations):
                    if (reservation.get("step_id") in step_ids
                            and reservation.get("status") == "reserved"
                            and not reservation.get("superseded")):
                        ledger.settle(reservation, actual=0,
                                      note="作者正文渲染拒绝且无交付痕迹，未调用，按零结算")
            state["feedback_refusal"] = {
                "ok": False, "codes": ["input.author_feedback_render"],
                "detail": str(error),
                "mode": state["plan"].get("author_feedback_mode", "full_v1"),
                "unissued_reservations_released": not handoff_exists,
            }
            state.setdefault("input_gaps", []).append("author_feedback_render：" + str(error))
            state["stop_reason"] = "author_feedback_render_refused"
            av_state_history_append(state, "INPUT_GAP", "作者反馈不能对账；本次未发新提示词，既有交付痕迹保守保留费用")
            return {"terminal": "INPUT_GAP"}
        pending = iter_dir / "pending" / state["plan"]["operator"]
        pending.mkdir(parents=True, exist_ok=True)
        (pending / "prompt.txt").write_text(packet.text, encoding="utf-8")
        context = gen._AvAttemptContext(state["plan"]["operator"], packet,
                                        {"facts": []})
        payload_for_tx = {
            "schema": "sitin-av-tx-model-call-before/1",
            "step": "GENERATED", "run_id": state["run_id"],
            "operator": state["plan"]["operator"],
            "prompt_sha256": packet.sha256, "prompt_chars": len(packet.text),
            "prompt_path": str(pending / "prompt.txt"),
            "parent": state["plan"].get("parent_dir"),
            "generation_mode": generation.get("mode"),
            "channel": "delegate-file-handoff",
            "request_params": {"backend": "delegate", "file_channel": True},
            "max_cost_reserved": dict(state.get("reservations") or {}),
            "note": "delegate 文件式通道：本进程不发请求；外部回复 envelope 出现后继续",
        }
        _av_tx_write(iter_dir, "model_call_before", payload_for_tx)
        gen.emit_prompt(context, iter_dir, backend="delegate")
        generation.update({"phase": "prompt_emitted",
                           "prompt_sha256": packet.sha256,
                           "pending_dir": str(pending)})
        if generation.get("mode") == "delegate":
            av_state_history_append(state, "RESERVED",
                                    "已产 delegate 交接件，等待外部回复 envelope")
            return {"waiting_for_reply": True}
        # mock 模式（显式测试模式）：直接合成回复继续。
    # —— 回复摄入（phase == prompt_emitted）。
    envelope_path = (Path(generation["reply_envelope"])
                     if generation.get("reply_envelope")
                     else iter_dir / "reply-envelope.json")
    if generation.get("mode") == "mock":
        from hangma_bot.policy.action_value_seeds import SEEDS

        seed = SEEDS[state["plan"]["seed_name"]]
        raw_reply = av_mock_model_reply(seed.source, "种子机制（mock 测试模式）",
                                        dict(seed.mechanism))
        usage = {}
        provider = model = None
        generation["provenance"] = "offline_mock_fixture"
    else:
        if not envelope_path.is_file():
            av_state_history_append(state, "RESERVED", "回复 envelope 未出现，继续等待")
            return {"waiting_for_reply": True}
        data = gen.load_reply_envelope(envelope_path,
                                       prompt_sha256=generation["prompt_sha256"])
        raw_reply = data["reply"]
        usage = data.get("usage") or {}
        provider, model = data.get("provider"), data.get("model")
        generation["provenance"] = data.get("origin")
    parsed = gen.parse_action_value_reply(raw_reply)
    code_text = gen.normalized_code(parsed["code"]) if parsed["code"] else None
    precheck = (gen.precheck_action_value_candidate(code_text)
                if code_text else {"ok": False, "problems": ["无代码"]})
    attempt_dir = iter_dir / "generation"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    (attempt_dir / "reply_raw.txt").write_text(raw_reply, encoding="utf-8")
    av_atomic_write_json(attempt_dir / "parsed.json", {
        "status": parsed["status"], "thought": parsed["thought"],
        "mechanism": parsed["mechanism"],
        "code_sha256": sha256_text(code_text) if code_text else None,
        "problems": parsed["problems"]})
    usage_known = bool(usage)
    _av_tx_write(iter_dir, "generation_complete", {
        "schema": "sitin-av-tx-generation-complete/1",
        "run_id": state["run_id"],
        "reply_path": str(attempt_dir / "reply_raw.txt"),
        "reply_sha256": sha256_text(raw_reply),
        "model": {"provider": provider, "model": model},
        "usage": usage if usage_known else None,
        "usage_unknown": not usage_known,
        "parse_status": parsed["status"], "precheck_ok": precheck["ok"],
        "mechanism_fields": sorted((parsed["mechanism"] or {}).keys()),
        "provenance": generation.get("provenance"),
    })
    # 结算生成 token：usage 已知按实结算；未知保守按预留额计费（不下调）。
    iteration_no = state["iteration_no"]
    for item in ledger.reservations:
        # 相同 step_id 的旧失败尝试会以 superseded 形式保留成本；新回复只结算在途行。
        if item.get("status") != "reserved" or item.get("superseded"):
            continue
        if item["step_id"] == "iter{0}:gen-tokens-in".format(iteration_no):
            ledger.settle(item, actual=(float(usage.get("input_tokens", 0))
                                        if usage_known else None),
                          usage_unknown=not usage_known)
        if item["step_id"] == "iter{0}:gen-tokens-out".format(iteration_no):
            ledger.settle(item, actual=(float(usage.get("output_tokens", 0))
                                        if usage_known else None),
                          usage_unknown=not usage_known)
    if parsed["status"] != gen.PARSE_OK or not precheck["ok"]:
        (attempt_dir / "candidate.py").write_text(code_text or "", encoding="utf-8") \
            if code_text else None
        state["rejection"] = {"reason": "生成解析或预检未通过",
                              "parse_status": parsed["status"],
                              "precheck": precheck}
        av_state_history_append(state, "REJECTED",
                                "生成失败（parse={0} precheck={1}）".format(
                                    parsed["status"], precheck["ok"]))
        return {"terminal": "REJECTED"}
    (attempt_dir / "candidate.py").write_text(code_text, encoding="utf-8")
    binding = gates.av_identity_binding(code_text)
    # 写 record.json（sitin-action-value-generation/1 同形状）：本机迭代产物
    # 可被 av_parent_binding 当 M1 父代绑定（与 batch7 产物同一合同）。
    av_atomic_write_json(attempt_dir / "record.json", {
        "schema": gen.AV_GENERATION_SCHEMA, "operator": state["plan"]["operator"],
        "backend": "delegate-file-channel",
        "created_at_utc": utc_now(),
        "identity": {"candidate_id": binding["candidate_id"]},
        "prompt": {"sha256": generation.get("prompt_sha256")},
        "parse": {"status": parsed["status"], "thought": parsed["thought"]},
        "precheck": precheck, "load": {"ok": True, "supervised": True},
        "note": "编排状态机生成产物（tx-generation-complete 见 transactions/）",
    })
    state["candidate_source"] = code_text
    state["identity"]["candidate_id"] = binding["candidate_id"]
    state["identity"]["candidate_source_sha256"] = sha256_text(code_text)
    generation.update({"phase": "ingested", "candidate_id": binding["candidate_id"],
                       "attempt_dir": str(attempt_dir)})
    # S3：生成事务的检查点（先落盘后提交状态）——中断后可据此对账，不重复摄入。
    av_checkpoint_write(iter_dir, AV_GENERATION_CHECKPOINT, {
        "status": "completed", "step": "GENERATED", "run_id": state["run_id"],
        "iteration_no": state["iteration_no"], "attempt_no": 1,
        "prompt_sha256": generation.get("prompt_sha256"),
        "reply_sha256": sha256_text(raw_reply),
        "candidate_id": binding["candidate_id"],
        "candidate_source_sha256": sha256_text(code_text),
        "attempt_dir": str(attempt_dir), "usage_unknown": bool(not usage_known),
        "tokens": {"input": (usage.get("input_tokens") if usage_known else None),
                   "output": (usage.get("output_tokens") if usage_known else None)},
    })
    av_fault_point("generate:after_ingest_before_state_save",
                   run_id=state["run_id"], candidate_id=binding["candidate_id"])
    av_state_history_append(state, "GENERATED", "回复已摄入并解析",
                            candidate_id=binding["candidate_id"])
    return {"advanced": "GENERATED"}


def _step_admit(state: Dict[str, Any]) -> Dict[str, Any]:
    admission = av_gates().admit_action_value(
        state["candidate_source"],
        facts_panel={"generator": av_opportunities().GENERATOR_SCRIPTED_FIXTURE,
                     "legal": True,
                     "record_dir": str(Path(state["iter_dir"]) / "admission")},
        timing_config={"repeats": 2})
    state["admission"] = {
        "candidate_id": admission["identity"]["candidate_id"],
        "execution_safety_pass": admission["execution_safety_pass"],
        "coverage": admission["layers"]["coverage"]["status"],
        "record_path": str(Path(state["iter_dir"]) / "admission" / "admission.json"),
    }
    if not admission["execution_safety_pass"]:
        state["rejection"] = {"reason": "执行安全层未通过（fail-closed）"}
        av_state_history_append(state, "REJECTED", "门禁执行安全层未通过")
        return {"terminal": "REJECTED"}
    av_state_history_append(state, "ADMITTED", "五层门禁执行安全 PASS",
                            coverage=admission["layers"]["coverage"]["status"])
    return {"advanced": "ADMITTED", "admission": admission}


#: 公共行为面板的**冻结可见观察集**（§9.4 顺序：行为面板在效果面板之前）。
#: 与门禁覆盖层 sitin_gates.AV_COVERAGE_VIEWS 同源；本常量是冻结期望，运行时
#: 逐字比对并把漂移记进 state.behavior（不静默接受两套清单）。
AV_BEHAVIOR_VIEWS: Tuple[str, ...] = (
    "fam_hu", "fam_pass", "fam_chi", "fam_peng", "fam_gang", "fam_discard",
    "route_combo", "unknown_missing",
)
AV_BEHAVIOR_SIGNATURE_SCHEMA = "sitin-av-behavior-signature/1"


def av_behavior_views() -> List[str]:
    """冻结可见观察集（取自门禁覆盖层，单一真相）+ 与冻结期望的漂移记录。"""

    declared = [str(name) for name in getattr(av_gates(), "AV_COVERAGE_VIEWS", ())]
    return declared or list(AV_BEHAVIOR_VIEWS)


def _av_behavior_signature(candidate_source: str, *,
                           real_panel: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """从**冻结可见观察集**计算行为签名：每窗**首选动作** + **未知掩码**（§9.2 规则 3）。

    首选动作 = 该窗口评分最高的 action_key；**本函数不再自己归约**——档案侧直接消费
    准入侧同实现的 `sitin_model_admission.preference_signature`，后者用生产排序
    （`hangma_bot.policy.action_value.batch_to_ranked_candidates`：原始分数降序、
    同分按 action_key 升序）定首选动作。

    为什么必须删掉档案侧的第二处归约（R9 §14 S3 自陈第二项）：档案此前对
    `behavior_signature` 的**分数向量**再取一次 argmax。两份实现"当前等价"不是
    保证——生产口径一变（例如改成先舍入再排序、或加入平分的二级键），档案侧就会
    与生产/准入分叉出第二套口径，而两份实现各自都"自洽"。统一到同一实现后，
    口径只有一个来源（P4 的 `PREFERENCE_ORDER_SOURCE`）。

    未知掩码 = 该窗口未取得可比评分（ABSTAIN/缺样本/执行失败）——缺证据如实标
    缺失，不把"没读到"当成某个动作。签名摘要在**值层面**去重：源码改名/改注释/
    改 trace 标签不改变签名，真正的评分变化才改变签名。
    """

    admission = _sibling("sitin_model_admission")
    views = av_behavior_views()
    raw = admission.preference_signature(candidate_source, views)
    windows: List[Dict[str, Any]] = []
    unknown_mask: Dict[str, bool] = {}
    for name in views:
        block = raw.get(name) or {}
        chosen = block.get("action_key")
        status = block.get("status")
        unknown_mask[name] = chosen is None
        windows.append({"window_id": name, "action_key": chosen,
                        "missing": chosen is None, "status": status})
    signature = {
        "schema": AV_BEHAVIOR_SIGNATURE_SCHEMA,
        "source": ("sitin_model_admission.preference_signature"
                   "（生产排序 batch_to_ranked_candidates，档案侧不二次归约）"),
        "view_set": views,
        "windows": windows,
        "unknown_mask": unknown_mask,
    }
    if real_panel is not None:
        declaration = av_development_behavior_panel(real_panel)
        real = _sibling("sitin_real_behavior")
        result = real.evaluate(candidate_source, Path(declaration["path"]))
        signature["schema"] = "sitin-av-behavior-signature/2"
        signature["real_panel"] = result
        prefix = "real:" + result["panel_digest"] + ":" + real.digest(result["execution_identity"]) + ":"
        for row in result["windows"]:
            name = prefix + row["window_id"]
            missing = row["status"] != "SCORED" or row["action_key"] is None
            windows.append({"window_id": name, "action_key": row["action_key"],
                            "status": row["status"], "missing": missing,
                            "plan_signature": None if missing else real.decision_signature(row)})
            unknown_mask[name] = missing
        signature["comparable"] = result["comparable"]
    signature["digest"] = (av_archive().behavior_signature_digest(signature)
                            if signature.get("comparable", True) else None)
    return signature


def _av_behavior_duplicates(entries: Mapping[str, Any], *, digest: Optional[str],
                            candidate_id: str) -> List[str]:
    """档案里与本次候选**行为签名相同**的其他身份（源码不同但动作相同）。"""

    if not digest:
        return []
    duplicates = []
    for cid in sorted(entries):
        if cid == candidate_id:
            continue
        entry = entries[cid] or {}
        other = entry.get("behavior_digest") or av_archive().behavior_signature_digest(
            entry.get("behavior_signature"))
        if other and other == digest:
            duplicates.append(cid)
    return duplicates


def _step_behavior(state: Dict[str, Any], run_root: Path) -> Dict[str, Any]:
    """公共行为面板步：覆盖（门禁）+ **行为签名**（冻结可见观察集）+ 源码/行为去重。

    去重分开记录（§9.2 规则 4）：源码去重按 candidate_id（源码身份），行为去重按
    行为签名摘要（首选动作 + 未知掩码）。同源码不同行为、同行为不同源码都能区分，
    不给同行为候选多余的探索名额。
    """

    # 在案档案按**运行链**读取（换 --out 时前序运行目录的档案才是比较基准）。
    known_archive = _av_previous_archive(state, run_root)
    entries = known_archive.get("entries") or {}
    candidate_id = state["identity"]["candidate_id"]
    source_duplicate = candidate_id in entries
    signature = None
    signature_error = None
    try:
        signature = _av_behavior_signature(state["candidate_source"],
                    real_panel=(state.get("plan") or {}).get("development_behavior_panel"))
    except Exception as exc:                              # noqa: BLE001
        signature_error = "{0}: {1}".format(type(exc).__name__, exc)
    digest = (signature or {}).get("digest")
    duplicates = _av_behavior_duplicates(entries, digest=digest,
                                         candidate_id=candidate_id)
    views = (signature or {}).get("view_set") or av_behavior_views()
    state["behavior"] = {
        "coverage": state["admission"]["coverage"],
        "source_fingerprint": candidate_id,
        "source_duplicate_in_archive": source_duplicate,
        "behavior_signature": signature,
        "behavior_digest": digest,
        "behavior_duplicate_in_archive": bool(duplicates),
        "behavior_duplicate_of": duplicates,
        "unknown_windows": sorted(name for name, missing
                                  in ((signature or {}).get("unknown_mask") or {}).items()
                                  if missing),
        "view_set_drift": (None if views == list(AV_BEHAVIOR_VIEWS)
                           else {"frozen": list(AV_BEHAVIOR_VIEWS), "observed": views}),
        "signature_error": signature_error,
        "dedup_note": ("候选身份已在档案（同 candidate_id）：源码去重命中；"
                       "行为去重按签名另行判定" if source_duplicate else "新候选身份"),
    }
    if (state.get("plan") or {}).get("development_behavior_panel") is not None and (
            signature_error is not None or signature is None or not signature.get("comparable")):
        state["stop_reason"] = "development_behavior_indeterminate"
        av_state_history_append(state, "INPUT_GAP", "真实行为面板不可判定，保留本次诊断且不评价/更新档案")
        return {"terminal": "INPUT_GAP"}
    av_state_history_append(state, "BEHAVIOR_CHECKED",
                            "覆盖+行为签名+源码/行为分别去重",
                            duplicate=source_duplicate or None,
                            behavior_duplicate=bool(duplicates) or None)
    return {"advanced": "BEHAVIOR_CHECKED"}


def _av_assemble_conditional_runtime(
        *, plan: Mapping[str, Any],
        test_runtime_factory: Optional[Callable[[], Mapping[str, Any]]] = None,
) -> Tuple[Mapping[str, Any], Dict[str, Any]]:
    """A1 修复：条件步的运行时装配（**组合处显式装配**）与装配记录。

    - 生产路径（test_runtime_factory 缺省）：经 build_real_runtime 装配组合根
      真实运行时（公开 start/frame/advance）；装配失败由调用方转终态，绝不回落
      替身/夹具；
    - 测试路径（test_runtime_factory 显式给出）：只能返回经显式测试入口
      build_test_runtime_double 装配的替身运行时（带 test_double 标签），否则拒绝
      ——替身在正式路径不可达，且产物会如实标 test_double 且不可用于选留。
    """

    opportunities = av_opportunities()
    from hangma_bot.kernel.config import RuleConfig

    if test_runtime_factory is not None:
        runtime = test_runtime_factory()
        kind = opportunities.runtime_kind_of(runtime)
        if kind != opportunities.RUNTIME_KIND_TEST_DOUBLE:
            raise opportunities.RuntimeAssemblyError(
                "test_runtime_factory 只能返回显式测试入口 build_test_runtime_double "
                "装配的替身运行时（得到 runtime_kind={0!r}）：真实运行时请走生产路径，"
                "不得用测试工厂冒充".format(kind))
        return runtime, {
            "entry": str(runtime.get("runtime_entry") or "test_runtime_factory"),
            "runtime_kind": kind,
            "execution_kind": opportunities.EXECUTION_TEST_DOUBLE,
            "engine_kind": opportunities.engine_kind_for(
                prefix_source="v2_behavior", runtime=runtime),
            "engine_identity": dict(runtime.get("engine_identity") or {}),
            "explicit_test_entry": True,
            "note": "显式测试入口注入的公开契约验证替身（0 真实桌赛；测试专用，"
                    "生产路径不可达；结果不可用于开发选留）",
        }
    runtime = opportunities.build_real_runtime(
        rules_config=RuleConfig(AV_CONDITIONAL_RULESET_VERSION, 1, False),
        rounds_per_game=AV_CONDITIONAL_ROUNDS_PER_GAME,
        seed=stage_seed_for_conditional(plan),
        scenario_id="sitin-av-conditional-{0}".format(plan.get("panel_seed")))
    return runtime, {
        "entry": str(runtime.get("runtime_entry") or "build_real_runtime"),
        "runtime_kind": opportunities.runtime_kind_of(runtime),
        "execution_kind": opportunities.EXECUTION_REAL,
        "engine_kind": opportunities.engine_kind_for(
            prefix_source="v2_behavior", runtime=runtime),
        "engine_identity": dict(runtime.get("engine_identity") or {}),
        "explicit_test_entry": False,
        "note": "组合处显式装配的组合根真实运行时（SimulationEngine 公开 "
                "start/frame/advance）",
    }


def stage_seed_for_conditional(plan: Mapping[str, Any]) -> int:
    """条件步真实运行时的装配种子（只影响组合根装配声明，不影响桌赛随机源）。"""

    return int(plan.get("panel_seed") or 0)


def av_conditional_step_prefix(state: Mapping[str, Any],
                               plan: Mapping[str, Any]) -> str:
    """条件面板的账步前缀（与 run_av_evaluation 的 step_id 同源）。"""

    candidate_id = str((state.get("identity") or {}).get("candidate_id") or "")
    return "evaluate:{0}:{1}".format(candidate_id[:12], plan.get("predicate"))


#: 条件面板**恢复三态**（评审 C6）。用 None 混同"没有完成记录"与"完成但损坏/不足"，
#: 会让坏证据沿"当作没有结果"重新评价，把改值结果洗成候选档案。
AV_CONDITIONAL_RECOVERY_ABSENT = "no_completion_record"
AV_CONDITIONAL_RECOVERY_VERIFIED = "verified"
AV_CONDITIONAL_RECOVERY_DAMAGED = "damaged"


def _av_reuse_conditional_evaluation(state: Dict[str, Any], plan: Mapping[str, Any],
                                     ) -> Dict[str, Any]:
    """S3/C6：条件面板已完成（事务件 + 不可变结果摘要 + 候选身份一致）→ 复用。

    返回**三态**（不再用 None 混同"没有记录"与"记录损坏"）：
      * no_completion_record = transactions/ 里没有完成事务件：本迭代尚未完成过该步，
        正常走评价（这是唯一允许重新评价的情形）；
      * verified = 完成事务件 + 不可变结果摘要 + 候选/面板身份逐项可核 ⇒ 复用
        （不重跑、不重复计费）；
      * damaged = 完成事务件**存在**但损坏或不足（读不出、结果文件缺失或不可读、缺摘要、
        摘要不符、候选或面板身份不符）⇒ **具名阻断**：状态不推进、不建档、不自动重跑。

    为什么 damaged 不能用 None 表示：调用方把 None 当"没有结果"，会重新装配运行时并再次
    评价（重新消耗预算），把坏证据洗成新结果；评审 C6 要求第三种必须具名阻断且不自动重跑。
    """
    iter_dir = Path(state["iter_dir"])
    tx_path = iter_dir / "transactions" / AV_TX_FILES["eval_conditional_complete"]

    def damaged(code: str, detail: str, **extra: Any) -> Dict[str, Any]:
        block = {"state": AV_CONDITIONAL_RECOVERY_DAMAGED, "code": code, "detail": detail,
                 "transaction_path": str(tx_path)}
        block.update(extra)
        return block

    if not tx_path.is_file():
        return {"state": AV_CONDITIONAL_RECOVERY_ABSENT, "code": None,
                "transaction_path": str(tx_path),
                "detail": "没有条件面板完成事务件：本迭代尚未完成过该步"}
    try:
        tx = json.loads(tx_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return damaged("COMPLETION_TRANSACTION_UNREADABLE",
                       "完成事务件无法读取：{0}: {1}".format(type(exc).__name__, exc))
    if not isinstance(tx, Mapping):
        return damaged("COMPLETION_TRANSACTION_MALFORMED",
                       "完成事务件不是对象（schema={0!r}）".format(type(tx).__name__))
    recorded = tx.get("immutable_summary_path")
    path = Path(recorded) if recorded else (iter_dir / "conditional" / "evaluation.json")
    if not path.is_file():
        return damaged("COMPLETION_RESULT_MISSING",
                       "完成事务件声明的不可变结果不存在：{0}".format(path),
                       recorded_path=(str(recorded) if recorded else None))
    recorded_sha = tx.get("immutable_summary_sha256")
    if not recorded_sha or not str(recorded_sha).strip():
        # 评审 C6 反例：改值 + 删摘要 ⇒ 旧实现直接复用，把 +0.5 写进 branch_open 档案。
        return damaged("COMPLETION_SUMMARY_DIGEST_MISSING",
                       "完成事务件缺少不可变结果摘要：无法核验结果是否被改写",
                       recorded_path=str(path))
    observed_sha = _av_file_digest(path)
    if str(recorded_sha) != observed_sha:
        return damaged("COMPLETION_SUMMARY_DIGEST_MISMATCH",
                       "不可变结果摘要与完成事务件登记值不一致（结果已被改写）",
                       recorded_sha256=str(recorded_sha), observed_sha256=observed_sha,
                       recorded_path=str(path))
    try:
        evaluation = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return damaged("COMPLETION_RESULT_UNREADABLE",
                       "不可变结果无法读取：{0}: {1}".format(type(exc).__name__, exc),
                       recorded_path=str(path))
    if not isinstance(evaluation, Mapping):
        return damaged("COMPLETION_RESULT_MALFORMED",
                       "不可变结果不是对象（schema={0!r}）".format(type(evaluation).__name__),
                       recorded_path=str(path))
    identity = dict(evaluation.get("identity") or {})
    recorded_candidate = str((state.get("identity") or {}).get("candidate_id") or "")
    if recorded_candidate and str(identity.get("candidate_id")) != recorded_candidate:
        return damaged("COMPLETION_IDENTITY_MISMATCH",
                       "完成事务件的候选身份与本次在案身份不一致",
                       expected_candidate_id=recorded_candidate,
                       observed_candidate_id=identity.get("candidate_id"),
                       recorded_path=str(path))
    predicate = (evaluation.get("panel") or {}).get("predicate")
    if predicate is not None and str(predicate) != str(plan.get("predicate")):
        return damaged("COMPLETION_PANEL_MISMATCH",
                       "完成事务件的面板谓词与本次计划不一致",
                       expected_predicate=plan.get("predicate"),
                       observed_predicate=predicate, recorded_path=str(path))
    block = {
        "ok": bool(evaluation.get("ok")),
        "evaluation_path": str(path),
        "evaluation_id": identity.get("evaluation_id"),
        "n_samples": len(evaluation.get("samples") or []),
        "execution_kind": evaluation.get("execution_kind"),
        "runtime_kind": evaluation.get("runtime_kind"),
        "engine_kind": evaluation.get("engine_kind"),
        "real_table_instances": evaluation.get("real_table_instances"),
        "double_table_instances": evaluation.get("double_table_instances"),
        "usable_for_selection": evaluation.get("usable_for_selection"),
        "result_admission": (evaluation.get("result_admission") or {}).get("ok"),
        "refused": evaluation.get("refused"),
        "reused_from_transaction": True,
        "immutable_summary_sha256": str(recorded_sha),
        "observed_summary_sha256": observed_sha,
    }
    return {"state": AV_CONDITIONAL_RECOVERY_VERIFIED, "code": None,
            "state_block": block, "evaluation": dict(evaluation),
            "transaction_path": str(tx_path), "recorded_sha256": str(recorded_sha),
            "observed_sha256": observed_sha}


def _step_conditional(state: Dict[str, Any], run_root: Path,
                      ledger: "ActionValueLedger",
                      authorization: Optional[Mapping[str, Any]],
                      test_runtime_factory: Optional[
                          Callable[[], Mapping[str, Any]]] = None) -> Dict[str, Any]:
    iter_dir = Path(state["iter_dir"])
    plan = state["plan"]
    # —— S3/C6 恢复对账：区分「没有完成记录」「已完成可核」「已完成但损坏/不足」——
    recovery = _av_reuse_conditional_evaluation(state, plan)
    if recovery["state"] == AV_CONDITIONAL_RECOVERY_DAMAGED:
        # 第三种必须**具名阻断**：状态不推进、不建档、不自动重跑（不得当作"没有结果"重新评价，
        # 否则既重复消耗预算，又把损坏证据洗成新结果）。
        refused = ("条件面板已完成的事务件损坏或不足（{0}）：{1}。"
                   "按 C6 口径具名阻断：状态不推进、不建档、不自动重跑。").format(
                       recovery["code"], recovery["detail"])
        state["conditional_recovery"] = {
            "state": recovery["state"], "code": recovery["code"],
            "detail": recovery["detail"],
            "transaction_path": recovery.get("transaction_path"),
            "recorded_path": recovery.get("recorded_path"),
            "recorded_sha256": recovery.get("recorded_sha256"),
            "observed_sha256": recovery.get("observed_sha256"),
            "refused": refused, "state_advanced": False, "archived": False,
            "auto_rerun": False, "cost_incurred": False,
        }
        state["conditional"] = {"ok": False, "status": "recovery_blocked",
                                "refused": refused,
                                "recovery": state["conditional_recovery"]}
        state["stop_reason"] = "conditional_recovery_blocked:{0}".format(recovery["code"])
        av_state_history_append(state, "EXECUTION_FAILED", refused,
                                recovery_code=recovery["code"])
        return {"terminal": "EXECUTION_FAILED"}
    if recovery["state"] == AV_CONDITIONAL_RECOVERY_VERIFIED:
        state["conditional_recovery"] = {
            "state": recovery["state"], "code": None,
            "transaction_path": recovery.get("transaction_path"),
            "recorded_sha256": recovery.get("recorded_sha256"),
            "observed_sha256": recovery.get("observed_sha256"),
            "state_advanced": True, "archived": False, "auto_rerun": False,
            "cost_incurred": False}
        state["conditional"] = recovery["state_block"]
        state["conditional_result"] = recovery["evaluation"]
        state["identity"]["evaluation_id"] = recovery["state_block"]["evaluation_id"]
        av_state_history_append(
            state, "CONDITIONAL_EVALUATED",
            "恢复：条件面板事务已提交且摘要逐项可核，复用不可变结果（不重跑、不重复计费）",
            evaluation_id=recovery["state_block"]["evaluation_id"])
        return {"advanced": "CONDITIONAL_EVALUATED", "restored": True}
    state["conditional_recovery"] = {"state": recovery["state"], "code": None,
                                     "detail": recovery.get("detail"),
                                     "transaction_path": recovery.get("transaction_path"),
                                     "auto_rerun": True, "state_advanced": False}
    # —— A1：运行时在组合处显式装配；缺省=真实组合根运行时，失败即终态 ——
    runtime: Optional[Mapping[str, Any]] = None
    if plan["prefix_source"] == "v2_behavior":
        opportunities = av_opportunities()
        try:
            runtime, assembly = _av_assemble_conditional_runtime(
                plan=plan, test_runtime_factory=test_runtime_factory)
        except opportunities.RuntimeAssemblyError as error:
            refused = ("条件面板运行时装配失败（A1 fail-closed：不回退替身/夹具）："
                       "{0}".format(error))
            state["plan"]["runtime_assembly"] = {
                "entry": "unavailable", "ok": False, "refused": refused,
                "runtime_kind": None, "execution_kind": None,
            }
            state["conditional"] = {"ok": False, "status": "runtime_assembly_missing",
                                    "refused": refused}
            state["stop_reason"] = "runtime_assembly_missing"
            _av_tx_write(iter_dir, "eval_conditional_begin", {
                "schema": "sitin-av-tx-eval-begin/1",
                "run_id": state["run_id"], "panel": "conditional",
                "task_list": {"predicate": plan["predicate"],
                              "opponent": plan["opponent"],
                              "arms": ["baseline", "candidate"], "seats": 1,
                              "schedule": "stage_complete"},
                "lease": {"worker_slots": 2, "purpose": "double-arm workers"},
                "runtime_assembly": state["plan"]["runtime_assembly"],
            })
            av_state_history_append(state, "EXECUTION_FAILED",
                                    "条件面板运行时装配失败（A1 fail-closed，不回退替身）")
            return {"terminal": "EXECUTION_FAILED"}
    else:
        assembly = {
            "entry": "scripted_fixture_engine", "ok": True,
            "runtime_kind": "scripted_fixture_engine",
            "execution_kind": "scripted_fixture",
            "engine_kind": "scripted_fixture_engine",
            "explicit_test_entry": False,
            "note": "夹具前缀路由（零真实桌赛）",
        }
    state["plan"]["runtime_assembly"] = dict(assembly, ok=True)
    _av_tx_write(iter_dir, "eval_conditional_begin", {
        "schema": "sitin-av-tx-eval-begin/1",
        "run_id": state["run_id"], "panel": "conditional",
        "task_list": {"predicate": plan["predicate"], "opponent": plan["opponent"],
                      "arms": ["baseline", "candidate"], "seats": 1,
                      "schedule": "stage_complete"},
        "lease": {"worker_slots": 2, "purpose": "double-arm workers"},
        "runtime_assembly": state["plan"]["runtime_assembly"],
    })
    # 运行时按来源走**不同的显式参数**：生产=真实运行时 runtime；测试=显式测试
    # 入口替身 test_runtime（run_av_evaluation 两者互斥并按标签校验种类）。
    # —— S3 恢复对账：旧尝试的账行先处理干净（在途→保守结算；已结算无结果→让位），
    #    再执行新尝试——已结算任务不再原地重复预留（费用保留、不重复计费）。
    conditional_prefix = av_conditional_step_prefix(state, plan)
    state["conditional_reconcile"] = {
        account: av_reconcile_ledger_attempts(
            ledger, step_prefix=conditional_prefix, account=account,
            reason="条件面板 {0}（旧尝试让位，失败成本保留）".format(account))
        for account in ("prefix_generation", "tables_partial", "tables_full")}
    runtime_kwargs: Dict[str, Any] = {}
    if runtime is not None:
        runtime_kwargs[("test_runtime" if assembly.get("explicit_test_entry")
                        else "runtime")] = runtime
    try:
        evaluation = run_av_evaluation(
            iter_dir / "conditional", state["candidate_source"],
            predicate=plan["predicate"], opponent=plan["opponent"],
            ledger=ledger, admission=None, authorization=authorization,
            prefix_source=plan["prefix_source"], attempts_cap=8,
            panel_seed=plan["panel_seed"], **runtime_kwargs)
    except BudgetExhausted:
        state["stop_reason"] = "budget_exhausted_conditional"
        av_state_history_append(state, "BUDGET_EXHAUSTED", "条件面板预算耗尽")
        return {"terminal": "BUDGET_EXHAUSTED"}
    except LedgerUnauthorized:
        state["stop_reason"] = "budget_unauthorized_conditional"
        av_state_history_append(state, "BUDGET_EXHAUSTED", "条件面板记账未授权")
        return {"terminal": "BUDGET_EXHAUSTED"}
    state["conditional"] = {
        "ok": bool(evaluation.get("ok")),
        "evaluation_path": str(iter_dir / "conditional" / "evaluation.json"),
        "evaluation_id": (evaluation.get("identity") or {}).get("evaluation_id"),
        "n_samples": len(evaluation.get("samples") or []),
        # A1(c)(d)：执行类别/引擎种类/桌赛实例数/可否选留一律取自评估产物
        # （评估产物又取自执行记录与装配对象）。
        "execution_kind": evaluation.get("execution_kind"),
        "runtime_kind": evaluation.get("runtime_kind"),
        "engine_kind": evaluation.get("engine_kind"),
        "real_table_instances": evaluation.get("real_table_instances"),
        "double_table_instances": evaluation.get("double_table_instances"),
        "usable_for_selection": evaluation.get("usable_for_selection"),
        "result_admission": (evaluation.get("result_admission") or {}).get("ok"),
        "refused": evaluation.get("refused"),
    }
    state["identity"]["evaluation_id"] = (evaluation.get("identity") or {}
                                          ).get("evaluation_id")
    _av_tx_write(iter_dir, "eval_conditional_complete", {
        "schema": "sitin-av-tx-eval-complete/1",
        "run_id": state["run_id"], "panel": "conditional",
        "evaluation_id": state["conditional"]["evaluation_id"],
        "valid": (evaluation.get("double_arm") or {}).get("valid"),
        "execution_kind": evaluation.get("execution_kind"),
        "runtime_kind": evaluation.get("runtime_kind"),
        "engine_kind": evaluation.get("engine_kind"),
        "runtime_assembly": state["plan"].get("runtime_assembly"),
        "cost": {
            # 费用与桌赛实例数来自执行记录（A1(d)），不再硬编码 0。
            "real_table_instances": int(evaluation.get("real_table_instances") or 0),
            "double_table_instances": int(evaluation.get("double_table_instances") or 0),
            "tables_full_executed": int((evaluation.get("panel") or {}).get(
                "tables_full_executed") or 0),
            "elapsed_ms_by_arm": {
                name: arm.get("elapsed_ms") for name, arm in
                ((evaluation.get("double_arm") or {}).get("arms") or {}).items()},
        },
        "result_admission": evaluation.get("result_admission"),
        "immutable_summary_path": state["conditional"]["evaluation_path"],
        # S3：不可变结果摘要进事务件——恢复对账据此判断"结果是否已被改写"。
        "immutable_summary_sha256": _av_file_digest(
            Path(state["conditional"]["evaluation_path"])),
    })
    state["conditional_result"] = evaluation
    av_state_history_append(state, "CONDITIONAL_EVALUATED",
                            "条件机会面板完成" if evaluation.get("ok")
                            else "条件面板未取得可用样本（insufficient 不伪装）",
                            evaluation_id=state["conditional"]["evaluation_id"])
    return {"advanced": "CONDITIONAL_EVALUATED"}


def _av_natural_instance_schedule(contract: Mapping[str, Any]) -> str:
    """赛程口径：一个实例=一个完整小组阶段（每臂 tables_per_group 桌）。"""

    return "stage_complete:{0}_tables".format(int(contract["group"]["tables_per_group"]))


def _av_natural_expected_instances(plan: Mapping[str, Any],
                                   contract: Mapping[str, Any],
                                   mix: str,
                                   *, candidate_id: Optional[str] = None
                                   ) -> List[Dict[str, Any]]:
    """本情景**预期实例清单**：完整评价身份（候选 × 对手情景 × 根 × 座位 × 臂 × 赛程）。

    清单在跑桌赛之前即可确定性算出（根 id 由 panel_seed+情景+根序号决定），
    因此"已开始"可以在真实副作用之前落盘。A3：候选身份必须进键——同一个运行目录
    内两次候选评价用同一根、同一座位、同一赛程时，旧键会撞成一条记录、后者的结果
    把前者顶掉（复审反例②）。候选以显式参数优先、其次取 plan.candidate_id。
    """

    natural = _sibling("sitin_natural_panel")
    schedule = _av_natural_instance_schedule(contract)
    roots = int(plan.get("natural_roots") or 1)
    seats = int(plan.get("natural_seats") or 1)
    tables = int(contract["group"]["tables_per_group"])
    seed = int(plan.get("panel_seed") or 0)
    owner = str(candidate_id or plan.get("candidate_id") or "")
    seed_of = getattr(natural, "natural_root_seed", None)
    rows: List[Dict[str, Any]] = []
    for root_index in range(1, roots + 1):
        root_id = natural.natural_root_id(mix, seed, root_index)
        root_seed = int(seed_of(seed, mix, root_index)) if seed_of else None
        for seat in range(seats):
            for arm in AV_INSTANCE_ARMS:
                rows.append(av_instance_row(
                    candidate_id=owner, opponent_mix=mix, panel_seed=seed,
                    source_root_id=root_id, root_index=root_index,
                    root_seed=root_seed, seat=seat, arm=arm, schedule=schedule,
                    planned_tables=tables))
    return rows


def _av_natural_result_instances(panel: Mapping[str, Any], expected: Sequence[Mapping[str, Any]],
                                 *, mix: str,
                                 result_path: Path) -> List[Dict[str, Any]]:
    """把面板结果落到实例粒度：费用（桌数）+ 不可变结果摘要（臂结果块摘要）。"""

    by_root_seat = {
        (str(sample.get("source_root_id")), int(sample.get("focal_anchor_seat") or 0)): sample
        for sample in (panel.get("samples") or [])}
    rows: List[Dict[str, Any]] = []
    for item in expected:
        sample = by_root_seat.get((str(item["source_root_id"]), int(item["seat"])))
        arm_block = None
        tables = 0
        if sample is not None:
            arm_block = (sample.get("arms") or {}).get(item["arm"])
            tables = len((((sample.get("raw_arms") or {}).get(item["arm"]) or {})
                          .get("tables") or []))
        row = dict(item)
        if arm_block:
            row.update({"status": "completed", "tables": tables,
                        "result_digest": sha256_text(canonical_json(arm_block)),
                        "result_path": str(result_path)})
        else:
            row.update({"status": "aborted", "tables": tables,
                        "result_digest": None,
                        "reason": "结果缺失（该根/座位/臂未产出样本）"})
        rows.append(row)
    return rows


def _av_panel_matches_plan(panel: Mapping[str, Any], *, plan: Mapping[str, Any],
                           mix: str,
                           expected: Sequence[Mapping[str, Any]]) -> Tuple[bool, str]:
    """对账判据：磁盘上的面板结果确实是**本次运行这一情景**的结果（不复用他者）。"""

    identity = panel.get("identity") or {}
    config = panel.get("config") or {}
    if str(identity.get("opponent_mix")) != str(mix):
        return False, "对手情景不符"
    if int(identity.get("panel_seed") or -1) != int(plan.get("panel_seed") or -2):
        return False, "面板种子不符"
    if int(config.get("roots") or 0) != int(plan.get("natural_roots") or 0):
        return False, "根数不符"
    if int(config.get("seats_per_root") or 0) != int(plan.get("natural_seats") or 0):
        return False, "座位数不符"
    roots = {str(sample.get("source_root_id"))
             for sample in (panel.get("samples") or [])}
    wanted = {str(item["source_root_id"]) for item in expected}
    if not wanted <= roots:
        return False, "根清单不符（{0} 未全部产出）".format(sorted(wanted - roots))
    return True, ""


def _step_natural(state: Dict[str, Any], run_root: Path,
                  authorization: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    iter_dir = Path(state["iter_dir"])
    plan = state["plan"]
    natural = _sibling("sitin_natural_panel")
    # —— Q6：统一**受信**授权校验（不再是散落的 "authorized is True and batch == 7"）——
    token_ok, auth_refusal, auth_audit = av_authorization_allows(
        authorization, operation="natural_panel",
        required=AV_AUTHORIZATION_OPERATION_REQUIREMENTS["natural_panel"])
    state["authorization"] = dict(auth_audit, planned={
        "tables_full": float(int(plan.get("natural_roots") or 1)
                             * int(plan.get("natural_seats") or 1) * 8.0),
        "opponents": list(plan.get("natural_opponents") or ("H", "M"))})
    # P2：授权档案条目（形态显式标注 + 逐项核对结论）随产物落盘。
    state["authorization_archive_entry"] = av_authorization_archive_entry(
        authorization, operation="natural_panel",
        required=AV_AUTHORIZATION_OPERATION_REQUIREMENTS["natural_panel"])
    if not token_ok:
        state["natural"] = {"status": "INPUT_GAP",
                            "reason": "自然面板未取得**受信**授权（Q6 统一校验）：{0}；"
                                      "缺授权标输入缺口，保留已取得条件证据".format(
                                          auth_refusal)}
        state.setdefault("input_gaps", []).append("natural_panel_authorization")
        av_state_history_append(state, "NATURAL_EVALUATED",
                                "自然面板输入缺口（无批次 7 令牌）")
        return {"advanced": "NATURAL_EVALUATED"}
    contract = json.loads(
        (_project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
         / "contracts/group-dev-v1.json")).read_text(encoding="utf-8"))
    # 声明混合要求 H 与 M 都在场：一次迭代跑两情景（各 natural_roots 根）。
    opponents = tuple(plan.get("natural_opponents") or ("H", "M"))
    candidate_id = str((state.get("identity") or {}).get("candidate_id") or "")
    iteration_no = int(state.get("iteration_no") or 0)
    run_id = str(state.get("run_id") or "")
    _av_tx_write(iter_dir, "eval_natural_begin", {
        "schema": "sitin-av-tx-eval-begin/1",
        "run_id": state["run_id"], "panel": "natural",
        "task_list": {"opponents": list(opponents),
                      "roots_per_opponent": plan["natural_roots"],
                      "seats_per_root": plan["natural_seats"],
                      "arms": ["baseline", "candidate"],
                      "schedule": "complete-group-stage(2 tables/arm)",
                      # S3：预期实例清单（来源根 × 座位 × 臂 × 赛程）先落盘，
                      # 与恢复时的实例台账对账。
                      "instance_keys": {
                          mix: [row["instance_key"] for row in
                                _av_natural_expected_instances(
                                    plan, contract, mix, candidate_id=candidate_id)]
                          for mix in opponents}},
        "lease": {"ledger": str(Path(run_root) / "av-ledger.json"),
                  "account": "tables_full"},
    })
    samples: List[Dict[str, Any]] = []
    panels: Dict[str, Any] = {}
    attempts: Dict[str, Any] = {}
    ledger = _av_ledger_for_run(run_root, authorization)
    # S3：H/M **逐情景**对账与检查点——H 完成、M 未完时中断，恢复只补 M。
    for mix in opponents:
        expected = _av_natural_expected_instances(plan, contract, mix,
                                                  candidate_id=candidate_id)
        panel_dir = iter_dir / ("natural-" + mix)
        panel_path = panel_dir / "panel.json"
        checkpoint = av_checkpoint_load(iter_dir, "natural-" + mix)
        step_prefix = "natural:{0}:{1}:".format(candidate_id[:12], mix)
        step_id = "{0}{1}".format(step_prefix, int(plan.get("natural_roots") or 1))
        planned_tables = float(sum(int(item["planned_tables"]) for item in expected))
        rows = av_ledger_rows_for_step(ledger, step_prefix=step_prefix,
                                       account="tables_full")
        previous_attempt = int((checkpoint or {}).get("attempt_no") or 0)
        panel: Optional[Mapping[str, Any]] = None
        reuse_reason: Optional[str] = None
        attempt_no = max(1, previous_attempt)
        if av_checkpoint_result_matches(checkpoint, panel_path):
            # 检查点 completed 且不可变结果摘要一致：直接复用（不重跑、不重复计费）。
            reuse_reason = "checkpoint"
            panel = json.loads(panel_path.read_text(encoding="utf-8"))
        elif panel_path.is_file() and rows:
            # 对账形态（②：结果写入与费用结算之间中断）：结果在盘上且身份/根清单
            # 与本情景一致 → 先按结果记录的执行数把在途账行结算干净，再采用结果。
            adopted: Optional[Mapping[str, Any]] = None
            try:
                adopted = json.loads(panel_path.read_text(encoding="utf-8"))
            except ValueError:
                adopted = None
            if isinstance(adopted, Mapping):
                matched, why = _av_panel_matches_plan(adopted, plan=plan, mix=mix,
                                                      expected=expected)
                source_sha = str((adopted.get("identity") or {}).get(
                    "candidate_source_sha256"))
                if matched and source_sha == sha256_text(state["candidate_source"]):
                    executed = int((adopted.get("cost") or {}).get(
                        "tables_full_executed") or 0)
                    reconcile = av_reconcile_ledger_attempts(
                        ledger, step_prefix=step_prefix, account="tables_full",
                        result_available=True, executed=float(executed),
                        reason="自然面板 {0}（结果在盘上，采用并结算）".format(mix))
                    attempts.setdefault(mix, {})["reconcile"] = reconcile
                    reuse_reason = "reconciled_result_on_disk"
                    panel = adopted
                else:
                    attempts.setdefault(mix, {})["reconcile_note"] = why
        if panel is None:
            # 新尝试：先把旧账行对账干净（在途保守结算 + 已结算让位，费用保留），
            # 再登记实例"已开始"（先落盘后执行），最后预留本尝试费用。
            attempt_no = previous_attempt + 1
            attempts.setdefault(mix, {})["reconcile"] = av_reconcile_ledger_attempts(
                ledger, step_prefix=step_prefix, account="tables_full",
                reason="自然面板 {0}（旧尝试让位，失败成本保留）".format(mix))
            av_instances_apply(iter_dir,
                               updates=[dict(item, status="started")
                                        for item in expected],
                               attempt_no=attempt_no, iteration_no=iteration_no,
                               run_id=run_id, mirror_root=run_root)
            av_checkpoint_write(iter_dir, "natural-" + mix, {
                "status": "started", "step": "NATURAL_EVALUATED", "mix": mix,
                "attempt_no": attempt_no, "run_id": run_id,
                "iteration_no": iteration_no, "step_id": step_id,
                "cost_planned": planned_tables, "cost_charged": None,
                "instance_keys": [item["instance_key"] for item in expected],
                "started_at_utc": utc_now(),
            })
            reservation = ledger.reserve(
                step_id=step_id, account="tables_full", amount=planned_tables,
                note="自然面板 {0}：{1} 根 × {2} 座位 × 2 臂 × {3} 桌".format(
                    mix, plan["natural_roots"], plan["natural_seats"],
                    int(contract["group"]["tables_per_group"])))
            av_fault_point("natural:{0}:after_reserve".format(mix), step_id=step_id)
            try:
                panel = natural.run_natural_panel(
                    candidate_source=state["candidate_source"], opponent=mix,
                    roots=plan["natural_roots"], seats_per_root=plan["natural_seats"],
                    contract=contract, out_dir=panel_dir,
                    authorization=authorization, panel_seed=plan["panel_seed"],
                    ledger_path=None)
            except SystemExit as exc:
                state["natural"] = {"status": "INPUT_GAP", "reason": str(exc)}
                state.setdefault("input_gaps", []).append(
                    "natural_panel_authorization")
                av_state_history_append(state, "NATURAL_EVALUATED", "自然面板授权缺口")
                return {"advanced": "NATURAL_EVALUATED"}
            except (BudgetExhausted, LedgerUnauthorized,
                   LedgerOverAuthorized) as exc:
                state["stop_reason"] = "budget_exhausted_natural"
                av_state_history_append(state, "BUDGET_EXHAUSTED",
                                        "自然面板预算耗尽：{0}".format(exc))
                return {"terminal": "BUDGET_EXHAUSTED"}
            av_fault_point("natural:{0}:after_result_before_settle".format(mix),
                           step_id=step_id)
            executed = int((panel.get("cost") or {}).get(
                "tables_full_executed") or 0)
            ledger.settle(reservation, actual=float(executed),
                          note="自然面板实跑桌赛实例 {0}/{1}（失败桌照记）".format(
                              executed, int(planned_tables)))
            av_fault_point("natural:{0}:after_settle_before_completion".format(mix),
                           step_id=step_id)
        # 身份投影统一：自然面板（B2 seeds 模块）用直接计算 id；编排状态机与
        # 门禁/条件样本用 S4 强化绑定 id（含第一方文件摘要）。同一源码的两种
        # id 在此归一到机器身份，**原始 id 保留在 panel_reported_candidate_id**
        # 供审计（不改数值证据，只统一身份投影）。归一在实例摘要之前，
        # 保证"新跑"与"复用磁盘结果"得到同一不可变摘要。
        canonical = state["identity"]["candidate_id"]
        for sample in panel.get("samples") or []:
            sample["panel_reported_candidate_id"] = sample.get("candidate_id")
            sample["candidate_id"] = canonical
            for arm in (sample.get("arms") or {}).values():
                if arm.get("candidate_id") not in (None, AV_BASELINE_ID):
                    arm["candidate_id"] = canonical
        samples.extend(panel.get("samples") or [])
        instance_report = av_instances_apply(
            iter_dir,
            updates=_av_natural_result_instances(panel, expected, mix=mix,
                                                 result_path=panel_path),
            attempt_no=attempt_no, iteration_no=iteration_no, run_id=run_id,
            mirror_root=run_root)
        av_checkpoint_write(iter_dir, "natural-" + mix, {
            "status": "completed", "step": "NATURAL_EVALUATED", "mix": mix,
            "attempt_no": attempt_no, "run_id": run_id,
            "iteration_no": iteration_no, "step_id": step_id,
            "cost_planned": planned_tables,
            "cost_charged": int((panel.get("cost") or {}).get(
                "tables_full_executed") or 0),
            "result_path": str(panel_path),
            "result_sha256": _av_file_digest(panel_path),
            "instance_keys": [item["instance_key"] for item in expected],
            "reused_from": reuse_reason, "instances": instance_report,
            "completed_at_utc": utc_now(),
        })
        attempts.setdefault(mix, {}).update({
            "reuse": reuse_reason, "step_id": step_id, "attempt_no": attempt_no,
            "planned_tables": int(planned_tables),
            "executed_tables": int((panel.get("cost") or {}).get(
                "tables_full_executed") or 0)})
        panels[mix] = panel
    state["natural"] = {
        "status": "ok",
        "panels": {mix: str(iter_dir / ("natural-" + mix) / "panel.json")
                   for mix in panels},
        "panel_path": str(iter_dir / "natural-H" / "panel.json"),
        "n_samples": len(samples),
        "tables_full_planned": sum(int((p.get("cost") or {}).get(
            "tables_full_planned") or 0) for p in panels.values()),
        "tables_full_executed": sum(int((p.get("cost") or {}).get(
            "tables_full_executed") or 0) for p in panels.values()),
        # S3：逐情景对账记录（复用/重试/结算，可事后核对不重不漏）。
        "attempts": attempts,
    }
    state["natural_result"] = {"samples": samples, "cost": {
        "tables_full_planned": state["natural"]["tables_full_planned"],
        "tables_full_executed": state["natural"]["tables_full_executed"]}}
    _av_tx_write(iter_dir, "eval_natural_complete", {
        "schema": "sitin-av-tx-eval-complete/1",
        "run_id": state["run_id"], "panel": "natural",
        "n_samples": state["natural"]["n_samples"],
        "cost": state["natural_result"]["cost"],
        "immutable_summary_path": state["natural"]["panels"],
        "immutable_summary_sha256": {
            mix: (_av_file_digest(Path(path)) if Path(path).is_file() else None)
            for mix, path in state["natural"]["panels"].items()},
        "attempts": attempts,
    })
    av_state_history_append(state, "NATURAL_EVALUATED",
                            "自然面板完成（H+M 声明混合）",
                            n_samples=state["natural"]["n_samples"])
    return {"advanced": "NATURAL_EVALUATED"}


def _av_dedupe_samples(samples: Sequence[Mapping[str, Any]],
                       ) -> Tuple[List[Mapping[str, Any]], List[Any]]:
    """S3：同一实例（情景 × 来源根 × 焦点座位）只让一份结果进统计。

    恢复复用/重试都不应让同一桌赛实例的结果重复入统计；重复项被丢弃并记入
    排除清单（不静默丢：调用方把条数写进 summary 与三段反馈）。
    """

    seen = set()
    kept: List[Mapping[str, Any]] = []
    dropped: List[Any] = []
    for sample in samples:
        key = (str(sample.get("scenario")), str(sample.get("source_root_id")),
               str(sample.get("focal_anchor_seat")))
        if key in seen:
            dropped.append({"scenario": key[0], "source_root_id": key[1],
                            "focal_anchor_seat": key[2]})
            continue
        seen.add(key)
        kept.append(sample)
    return kept, dropped


def _av_split_selectable(samples: Sequence[Mapping[str, Any]]) -> Tuple[List, List]:
    """A1：把**显式标为不可选留**的样本（替身/夹具执行）与可选留样本分开。

    只有明确 `selection_eligible is False` 的样本被排除（不猜缺字段：自然面板等
    其他来源样本未标该字段时按原行为参与），排除量记入 summary 与反馈，不静默丢弃。
    """

    selectable: List[Mapping[str, Any]] = []
    excluded: List[Mapping[str, Any]] = []
    for sample in samples:
        (excluded if sample.get("selection_eligible") is False
         else selectable).append(sample)
    return selectable, excluded


def _av_selection_notes(state: Mapping[str, Any], *, n_selectable: int,
                        excluded: Sequence[Any], deduped: Sequence[Any],
                        natural: Mapping[str, Any]) -> Dict[str, Any]:
    """选留口径说明（写盘供反馈投影当证据用）：排除量/去重量/自然面板样本数。

    R7/P9：这些计数在旧实现里只是拼进 facts 的一句话（读者无从核对）。现在它们
    先落成产物 `summary/selection-notes.json`，反馈投影按 JSON 定位引用同一读数，
    条目因此可逐项对账。
    """

    notes: List[Dict[str, str]] = []
    if natural:
        notes.append({
            "key": "natural_panel_samples",
            "text": "自然面板：{0} 样本（tables_full 实跑 {1}）".format(
                natural.get("n_samples"), natural.get("tables_full_executed")),
        })
    if excluded:
        notes.append({
            "key": "excluded_non_selectable",
            "text": ("非真实运行时样本 {0} 个已排除（A1：替身/夹具结果不参与统计与"
                     "选留；已排除样本的原始产物保留在条件面板目录）").format(
                         len(excluded)),
        })
    if deduped:
        notes.append({
            "key": "deduped_instances",
            "text": "重复实例样本 {0} 个已去重（S3：同一情景×根×座位只进统计一次）".format(
                len(deduped)),
        })
    return {
        "schema": "sitin-av-selection-notes/1",
        "run_id": state.get("run_id"),
        "iteration_no": state.get("iteration_no"),
        "n_samples_selectable": int(n_selectable),
        "n_samples_excluded_non_selectable": len(excluded),
        "n_samples_deduped": len(deduped),
        "notes": notes,
    }


def _av_parent_candidate_id(state: Mapping[str, Any]) -> Optional[str]:
    """本迭代父代的候选身份：优先计划登记值，否则**按父代产物重算**。

    R9/P5（复审 R8 §6 F2）：M1 的父代必须写进反馈身份——"这份反馈是给哪个候选的"
    要能逐项核对，而不是留一个 None 让消费端自己去猜。
    """

    plan = state.get("plan") or {}
    recorded = plan.get("parent_candidate_id")
    if recorded:
        return str(recorded)
    parent_dir = plan.get("parent_dir")
    if not parent_dir:
        return None
    try:
        return str(av_generate().av_parent_binding(Path(parent_dir))["candidate_id"])
    except Exception:  # noqa: BLE001 - 绑不上就如实留 None（消费端会拒绝放行）
        return None


def _step_summarize(state: Dict[str, Any]) -> Dict[str, Any]:
    """NATURAL_EVALUATED→SUMMARIZED：根级统计 + 三段反馈（**共享投影**，R7/P9）。

    反馈的事实与关联结果一律从**已验证产物**生成：本步先写
    `summary/statistics.json`（已做替身/夹具排除与同实例去重）与
    `summary/selection-notes.json`，再由 `tools/sitin_feedback.py` 的同一投影读
    条件面板 / 机会面板 / 自然面板 / 上述两份产物，逐条带证据（产物 + 定位 + 原值）。
    投影判定 `executable=False`（误绑定 / 缺读数 / 确认数据混入）时**照写反馈**并
    记录拒绝码；下游 M1 生成步据此拒绝产出可执行修订任务。
    """

    iter_dir = Path(state["iter_dir"])
    samples = []
    evaluation = state.get("conditional_result") or {}
    samples.extend(evaluation.get("samples") or [])
    panel = state.get("natural_result") or {}
    samples.extend(panel.get("samples") or [])
    # A1：替身/夹具执行的样本不参与根级统计与效果反馈（如实记录排除量）。
    selectable, excluded = _av_split_selectable(samples)
    # S3：同一实例（情景×根×座位）只进统计一次——恢复复用/重试不产生重复样本。
    selectable, deduped = _av_dedupe_samples(selectable)
    statistics = av_archive().paired_stage_statistics(selectable, min_roots=1)
    summary_dir = iter_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    av_atomic_write_json(summary_dir / "statistics.json", statistics)
    notes = _av_selection_notes(
        state, n_selectable=len(selectable), excluded=excluded, deduped=deduped,
        natural=(state.get("natural") or {}) if panel else {})
    notes_path = summary_dir / "selection-notes.json"
    av_atomic_write_json(notes_path, notes)
    identity = state.get("identity") or {}
    feedback = build_three_segment_feedback(
        evaluation, eval_dir=iter_dir,
        candidate_cid=identity.get("candidate_id"),
        parent_cid=_av_parent_candidate_id(state))
    av_atomic_write_json(summary_dir / "feedback.json", feedback)
    state["summary"] = {
        "statistics_path": str(summary_dir / "statistics.json"),
        "selection_notes_path": str(notes_path),
        "feedback_path": str(summary_dir / "feedback.json"),
        "feedback_schema": feedback.get("schema"),
        "feedback_status": feedback.get("status"),
        "feedback_executable": bool(feedback.get("executable")),
        "feedback_refusal_codes": [item.get("code")
                                   for item in feedback.get("refusals") or []],
        "n_samples": len(selectable),
        "n_samples_excluded_non_selectable": len(excluded),
        "n_samples_deduped": len(deduped)}
    if not feedback.get("executable"):
        state.setdefault("input_gaps", []).append(
            "feedback_not_executable：{0}".format(
                "；".join("{0}={1}".format(item.get("code"), item.get("detail"))
                         for item in feedback.get("refusals") or [])))
    av_state_history_append(state, "SUMMARIZED", "根级统计与三段反馈（共享投影）",
                            n_samples=len(selectable),
                            excluded=len(excluded) or None,
                            deduped=len(deduped) or None,
                            feedback_status=feedback.get("status"))
    return {"advanced": "SUMMARIZED"}


def _av_normal_root_records(state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """正常通道根记录（root_id/opponent_mix），来自自然面板样本。"""

    panel = state.get("natural_result") or {}
    roots: Dict[str, str] = {}
    for sample in panel.get("samples") or []:
        roots[sample["source_root_id"]] = sample.get("opponent_mix")
    return [{"root_id": rid, "opponent_mix": mix} for rid, mix in sorted(roots.items())]


def _av_archive_entries_with(state: Mapping[str, Any],
                             previous: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """持久档案条目合并：旧 entries + 本迭代新条目（不重建单候选档案）。

    A3：本迭代证据按**完整根身份增量合并**进该候选的既有条目（补齐而不覆盖）——
    同候选补 M 情景/补代价侧/补新根都不会丢掉之前已取得的根证据；行为签名来自
    行为步（冻结可见观察集），随条目落档供探索席去重使用。
    """

    archive_mod = av_archive()
    samples = []
    evaluation = state.get("conditional_result") or {}
    samples.extend(evaluation.get("samples") or [])
    panel = state.get("natural_result") or {}
    samples.extend(panel.get("samples") or [])
    # A1：替身/夹具执行的样本不得进入开发选留（建档/席位），单独留档不混算。
    selectable, excluded = _av_split_selectable(samples)
    candidate_id = state["identity"]["candidate_id"]
    behavior_signature = (state.get("behavior") or {}).get("behavior_signature")
    pool = dict(previous.get("entries") or {})
    if selectable:
        pool[candidate_id] = archive_mod.merge_archive_entry(
            pool.get(candidate_id), candidate_id, selectable, safety="PASS",
            behavior_signature=behavior_signature)
    elif excluded:
        # 只有非真实运行时的样本：**不建档**（不把替身/夹具结果当候选证据），
        # 记输入不足，交由调度在缺证据时按原语义处理。
        state.setdefault("input_gaps", []).append(
            "no_selectable_samples_for_archive（条件样本非真实运行时）")
    return [pool[cid] for cid in sorted(pool)]


def _av_chain_archive_dirs(state: Mapping[str, Any], run_root: Path) -> List[Path]:
    """**同一运行链**上的档案目录（A2：档案/epoch/根台账/历史必须同源传递）。

    顺序：本运行目录 archive/ → 开轮时记下的调度输入档案所在目录
    （state.plan.archive_in.path 的父目录）→ 兄弟 iter-* 运行目录。换 --out 时
    本地没有档案/epoch/根台账，本函数把它们从链上前序运行目录接过来——不继承
    就会"新目录自建 epoch"，从而绕过通道挑战（复审 §4 A2 第二处）。
    """

    run_root = Path(run_root)
    dirs: List[Path] = [run_root / "archive"]
    recorded = ((state.get("plan") or {}).get("archive_in") or {}).get("path")
    if recorded:
        dirs.append(Path(recorded).parent)
    for root in _av_chain_run_roots(run_root)[1:]:
        dirs.append(Path(root) / "archive")
        dirs.append(Path(root))
    out: List[Path] = []
    seen = set()
    for directory in dirs:
        key = str(directory)
        if key in seen:
            continue
        seen.add(key)
        out.append(directory)
    return out


def _av_inherited_epoch(state: Mapping[str, Any], run_root: Path
                        ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """本通道在案的正常通道 epoch（同一运行链上最近的一份）。

    返回 (epoch, 来源记录)；没有则 (None, {"source": "none"})——调用方据此走
    "首次提交建立 epoch"分支（此时**没有**在案席位可比，不做通道挑战）。
    """

    run_root = Path(run_root)
    recorded = ((state.get("plan") or {}).get("archive_in") or {}).get("path")
    for directory in _av_chain_archive_dirs(state, run_root):
        path = Path(directory) / "normal-epoch.json"
        if not path.is_file():
            continue
        if Path(directory) == run_root / "archive":
            source = "local"
        elif recorded and Path(directory) == Path(recorded).parent:
            source = "archive_in"
        else:
            source = "chain"
        return (json.loads(path.read_text(encoding="utf-8")),
                {"source": source, "path": str(path), "dir": str(directory)})
    return None, {"source": "none", "path": None, "dir": None}


def _av_baseline_archive(state: Mapping[str, Any], run_root: Path, *,
                         prefer_dir: Optional[str] = None) -> Dict[str, Any]:
    """事务基准档案：**原席位**与在案条目（A2）。

    优先取与在案 epoch **同一目录**的那一份（席位与根集必须同源）；否则回落到
    _av_previous_archive（本目录 → 调度输入档案 → 迭代目录链 → 空档案）。
    """

    if prefer_dir:
        path = Path(prefer_dir) / "av-archive.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return _av_previous_archive(state, run_root)


def _av_baseline_slots(baseline: Mapping[str, Any],
                       pool_view: Mapping[str, Any]) -> Dict[str, List[str]]:
    """原席位快照：在案档案席位原样复制；在案无席位时才退回候选池重排结果。"""

    baseline_slots = {channel: list(ids or [])
                      for channel, ids in (baseline.get("slots") or {}).items()}
    if any(baseline_slots.values()):
        return baseline_slots
    return {channel: list(ids or [])
            for channel, ids in (pool_view.get("slots") or {}).items()}


#: **不需要同根挑战**的通道（A4）：探索席由公共行为面板（行为签名最小距离最大化）
#: 决定，与任何通道的根集无关。把它一起"换回原席"会让探索父代通道永远空着。
AV_PANEL_ONLY_CHANNELS: Tuple[str, ...] = ("exploration",)


def _av_frozen_seats(baseline_seats: Mapping[str, Any]) -> Dict[str, List[str]]:
    """冻结面席位：在案席位原样，**探索席置空**。

    探索席由提交点相对**提交后的在案席位**重算（见 `_av_commit_slots`），因此冻结面
    一律不带探索席：先置空可保证任何路径都不会把上一轮的探索席当成本次结论，也不会
    把「面板视角的探索席」与「冻结的在案席位」拼在一起（R9 计划 §13 A 的缺陷机制）。
    """

    seats = {channel: list(ids or [])
             for channel, ids in (baseline_seats or {}).items()}
    for channel in AV_PANEL_ONLY_CHANNELS:
        seats[channel] = []
    return seats


def _av_commit_slots(archive: MutableMapping[str, Any],
                     seats: Mapping[str, Any]) -> Dict[str, Any]:
    """把「冻结的挑战通道席位 + 相对这些在案席位重算的探索席」一次写入 archive。

    R9 计划 §13 A 项（Lead 裁定）：探索席必须相对**提交后的在案席位**重算——
    排除在案 overall 与四个家族席持有者，并用**这些持有者的行为签名摘要**做同行为
    去重参考；口径实现唯一来源 = `sitin_archive.select_exploration_seat`
    （`rebase_exploration_seat` 是它的整体重算入口，`update_archive` 用同一函数）。

    一并更新 `selection_report` 与 `distinct_candidates`：不留下"报告说 A、席位是 B"
    的错账。资格不放宽（安全 PASS、非 V2、非故障未修复、须有行为签名证据），本函数
    只搬运结论，不改任何通道自身的挑战/epoch 语义。
    """

    rebased = av_archive().rebase_exploration_seat(archive, slots=seats)
    archive["slots"] = rebased["slots"]
    archive["selection_report"] = rebased["selection_report"]
    archive["distinct_candidates"] = rebased["distinct_candidates"]
    archive["slot_selection_version"] = rebased["slot_selection_version"]
    return archive["slots"]


def _av_record_normal_roots(run_root: Path, state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """正常根台账（archive/normal-roots.json）：跨迭代累积 {root_id, opponent_mix}。

    通道 epoch 按**全部已取得自然根的并集**构建（声明混合需 H 与 M 都在场；
    缺一侧记输入缺口，不伪装可比较）。A2：并集含**同一运行链**前序运行目录的
    根台账——换 --out 只继承档案不继承根台账会让根集静默回退（复审 §4 A2）。
    """

    ledger_path = Path(run_root) / "archive" / "normal-roots.json"
    roots: Dict[str, str] = {}
    for directory in _av_chain_archive_dirs(state, run_root):
        chain_path = Path(directory) / "normal-roots.json"
        if not chain_path.is_file():
            continue
        for row in json.loads(chain_path.read_text(encoding="utf-8")).get("roots", []):
            roots[row["root_id"]] = row.get("opponent_mix")
    for row in _av_normal_root_records(state):
        roots[row["root_id"]] = row.get("opponent_mix")
    payload = {"schema": "sitin-av-normal-roots/1",
               "roots": [{"root_id": rid, "opponent_mix": mix}
                         for rid, mix in sorted(roots.items())]}
    av_atomic_write_json(ledger_path, payload)
    return payload["roots"]


def _av_commit_archive(state: Dict[str, Any], run_root: Path,
                       attempt_refresh: bool,
                       refresh_budget: Optional[int] = None) -> Dict[str, Any]:
    """档案提交/通道刷新（§9.2「补根成功才换席」；A2 事务化）。

    事务基准 = **原席位 + 通道根集 + epoch**，三者取自同一运行链（本运行目录 →
    调度输入档案目录 → 兄弟 iter-* 运行目录）。候选池重排（update_archive）只产出
    **候选池视角**（entries 与池内排序报告），绝不直接落席：

      ① 挑战者先补该通道当前全部根（阶段 1，apply_challenge 内）；
      ② 有望入席后，为本次全部参与重排者补齐声明的刷新根（阶段 2）；
      ③ 全部完成后统一提交新 epoch 并重排（原子；persist_dir 落全员补根材料）。

    任一非 committed 结局（部分完成 / 刷新批校验异常 / 预算不足 / 挑战者不可排序
    / 未请求刷新）一律**保留原席与原 epoch**：新候选只留在候选池（entries）或探索
    候选队列（pending），不写新 epoch。档案、epoch、根台账、历史沿运行链传递
    （换 --out 也继承，不因换目录自建 epoch 绕过挑战——复审 §4 A2）。
    """

    archive_mod = av_archive()
    archive_dir = Path(run_root) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / "av-archive.json"
    epoch_path = archive_dir / "normal-epoch.json"
    iter_dir = Path(state["iter_dir"])
    candidate_id = state["identity"]["candidate_id"]
    # 增量提交基数：本目录档案 → 开轮时记下的调度输入档案 → 迭代目录链最新一份
    # → 空档案（跨 --out iter-NN 的链上合并，不把在案条目截断成单候选）。
    previous = _av_previous_archive(state, run_root)
    # 同一运行链上的在案 epoch 与基准档案（换 --out 也继承；不继承即绕过挑战）。
    epoch, epoch_prov = _av_inherited_epoch(state, run_root)
    baseline = _av_baseline_archive(state, run_root,
                                    prefer_dir=epoch_prov.get("dir"))
    entries = _av_archive_entries_with(state, previous)
    new_roots = _av_normal_root_records(state)
    # 根台账随运行链累积（epoch 根集由它派生；换目录不重置）。
    union_roots = _av_record_normal_roots(run_root, state)
    # 候选池视角：池内排序与报告用；**不作在案席位**。
    pool_view = archive_mod.update_archive(entries)
    baseline_seats = _av_baseline_slots(baseline, pool_view)
    seats_before = list(baseline_seats.get("overall", ()))
    current_epoch_ids = [row["root_id"] for row in (epoch or {}).get("roots", ())]
    # 挑战基准档案：席位 = **需要同根挑战的通道的原席**（探索席不参与挑战——它在
    # 提交点相对提交后的席位重算，见 _av_commit_slots / R9 §13 A），条目 = 合并后的
    # 候选池（原席者与挑战者证据都在）。
    challenge_base = dict(pool_view)
    challenge_base["slots"] = _av_frozen_seats(baseline_seats)

    def _tx(payload: Dict[str, Any]) -> None:
        record = {"schema": "sitin-av-tx-channel-refresh/1",
                  "run_id": state["run_id"], "epoch_source": epoch_prov,
                  "seats_before": seats_before,
                  "refresh_roots_declared": [row["root_id"] for row in new_roots],
                  "refresh_roots_reserved": [row["root_id"] for row in new_roots
                                             if row["root_id"] not in current_epoch_ids],
                  "challenger_kept_in_pool": candidate_id in pool_view["entries"]}
        record.update(payload)
        _av_tx_write(iter_dir, "channel_refresh", record)

    def _kept(status: str, note: str, *, phase: Any = None, missing: Any = None,
              extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """非提交结局：**需要同根挑战的通道**保留原席与原 epoch（新候选只留候选池/队列）。

        A4/§13 A：冻结面只覆盖需要同根挑战的通道；探索席相对**提交后的在案席位**
        重算（排除在案 overall 与四家族席持有者 + 同行为去重），随本次档案事务
        **一并提交**（同一份原子写，不另开旁路）。
        """

        kept = dict(pool_view)
        _av_commit_slots(kept, _av_frozen_seats(baseline_seats))
        queue = [cid for cid in (baseline.get("exploration_queue") or [])
                 if isinstance(cid, str)]
        for cid in ((extra or {}).get("exploration_queue") or []):
            if isinstance(cid, str) and cid not in queue:
                queue.append(cid)
        if candidate_id in kept.get("entries", {}) and candidate_id not in queue:
            queue.append(candidate_id)
        kept["exploration_queue"] = queue
        kept["challenge"] = {"status": status, "phase": phase, "seats_kept": True,
                             "epoch_kept": (epoch or {}).get("epoch"),
                             "note": note}
        # epoch 原样落盘：本地没有时即从链上继承（内容不变，仍是原 epoch）。
        av_atomic_write_json(epoch_path, epoch)
        av_atomic_write_json(archive_path, kept)
        refresh: Dict[str, Any] = {
            "status": status, "note": note, "phase": phase, "missing": missing,
            "seats_kept": True, "epoch_kept": (epoch or {}).get("epoch"),
            "seats_after": list(kept["slots"].get("overall", ())),
            # A4：探索席不在冻结面内，如实报出本次提交后的探索席（可逐次核对）。
            "exploration_after": list(kept["slots"].get("exploration", ()))}
        if isinstance(extra, Mapping):
            for key in ("budget", "needed", "exploration_queue", "challenger_value",
                        "incumbent_values"):
                if key in extra:
                    refresh[key] = extra[key]
        _tx({"old_epoch": {"epoch_no": (epoch or {}).get("epoch"),
                           "roots": current_epoch_ids},
             "outcome": status, "phase": phase, "missing": missing, "note": note,
             "seats_after": list(kept["slots"].get("overall", ())),
             "exploration_after": list(kept["slots"].get("exploration", ()))})
        return {"status": ("REFRESH_PENDING" if status == "pending_partial"
                           else "ARCHIVE_COMMITTED"),
                "archive": kept, "refresh": refresh}

    if epoch is None:
        # 首次提交：建立正常通道 epoch——根集=**同一运行链全部自然根并集**（声明
        # 混合需 H 与 M 都在场；缺一侧记输入缺口，不填零争席也不伪装可比较）。
        mixes = {row.get("opponent_mix") for row in union_roots}
        epoch_new = None
        if union_roots and mixes >= {"H", "M"}:
            epoch_new = archive_mod.build_channel_epoch("normal", union_roots)
            av_atomic_write_json(epoch_path, epoch_new)
        elif union_roots:
            state.setdefault("input_gaps", []).append(
                "normal_channel_epoch_mix_incomplete:{0}".format(sorted(mixes)))
        archive_new = dict(pool_view)
        archive_new["challenge"] = {
            "status": "epoch_established", "seats_kept": False, "epoch_kept": None,
            "note": "在案无 epoch：本迭代建立通道 epoch 与初始席位（无在案席位可比）"}
        # A4/P7（R9 §15 P6 未闭合项 2）：首次提交分支**显式走同一套提交口径**。
        # 本分支的在案席位就是候选池视角的席位（无冻结、无挑战），因此探索席此前已
        # 相对同一席位算过，拼接缺陷不会在此复发；但"结论相同"是**旁证**、不是保证——
        # 一旦这里改成先写席再补探索席、或池内视角与提交席位分叉，就会静默回到
        # §13 A 的旧缺陷形态。统一调用后口径只有一个入口（_av_commit_slots →
        # sitin_archive.rebase_exploration_seat），等价性由 P7 证据逐字节对照证明
        # （archive/av-archive.json 与事务件），不靠注释里的一句"应当相同"。
        _av_commit_slots(archive_new, _av_frozen_seats(archive_new.get("slots") or {}))
        av_atomic_write_json(archive_path, archive_new)
        _tx({"old_epoch": None, "outcome": "epoch_established",
             "new_epoch": (epoch_new or {}).get("epoch"),
             "seats_after": list(archive_new["slots"].get("overall", ())),
             # A4/P7：与其它提交点同一记账口径——本次提交后的探索席一并入账
             # （此前只有保席/挑战提交分支记这一项，首次提交的探索席在事务件里不可见）。
             "exploration_after": list(
                 archive_new["slots"].get("exploration", ()))})
        return {"status": "ARCHIVE_COMMITTED", "archive": archive_new,
                "refresh": {"status": "epoch_established", "seats_kept": False,
                            "epoch": (epoch_new or {}).get("epoch")}}

    # —— 挑战前的两道**诚实前置判定**（提交权仍在 apply_challenge，见下）——
    if not attempt_refresh:
        return _kept("no_refresh_requested",
                     "调用方未请求刷新：保持旧 epoch 旧席位，不触发通道重排")
    challenger_entry = pool_view["entries"].get(candidate_id, {}) or {}
    challenger_evals = challenger_entry.get("normal_evaluations") or {}
    phase1_missing = [rid for rid in current_epoch_ids if rid not in challenger_evals]
    if phase1_missing:
        # §9.2 阶段 1：挑战者先补齐该通道当前全部根；未补齐不比较、不重排。
        return _kept("pending_partial",
                     "挑战者未补齐通道当前全部根（阶段 1）：原席原 epoch 保持，"
                     "结果暂存 pending",
                     phase="phase1", missing={candidate_id: phase1_missing})
    challenger_sortable = ((challenger_entry.get("overall") or {}
                            ).get("sort_value") is not None)
    if not challenger_sortable:
        return _kept("challenger_not_sortable",
                     "挑战者缺完整声明混合（H+M）正常排序值：无法同根集比较，"
                     "保持原席原 epoch")
    refresh_roots = [row for row in new_roots if row["root_id"] not in current_epoch_ids]
    try:
        outcome: Mapping[str, Any] = archive_mod.apply_challenge(
            challenge_base, epoch, candidate_id,
            evaluations={candidate_id: {}},
            refresh_roots=refresh_roots,
            budget=refresh_budget,
            persist_dir=archive_dir)
    except ValueError as exc:
        # 刷新批校验异常（如"0 个新根而非 4 根"）不是"无望入席"：原席原 epoch 保持。
        outcome = {"status": "refresh_rejected", "note": str(exc)}
    if not isinstance(outcome, Mapping):
        outcome = {"status": "refresh_rejected", "note": "挑战返回非映射结果"}
    if outcome.get("status") == "committed":
        new_epoch = outcome["new_epoch"]
        archive_new = dict(outcome["archive"])
        # A4/§13 A：挑战提交后**重算**探索席——挑战可能已经换了本通道席位，排除集
        # 与去重参考必须取**提交后**的在案席位，不能沿用挑战前的（同源漏洞）。
        _av_commit_slots(archive_new, _av_frozen_seats(archive_new.get("slots") or {}))
        archive_new["challenge"] = {
            "status": "committed", "seats_kept": False,
            "epoch_before": outcome.get("epoch_before"),
            "epoch_after": new_epoch.get("epoch"),
            "participants": sorted(outcome.get("ranking") and
                                   [row["candidate_id"] for row in outcome["ranking"]]
                                   or [candidate_id]),
            "note": "全员补根齐备 → 原子提交新 epoch 并用新根集统一重排"}
        av_atomic_write_json(epoch_path, new_epoch)
        av_atomic_write_json(archive_path, archive_new)
        _tx({"old_epoch": {"epoch_no": epoch.get("epoch"),
                           "roots": current_epoch_ids},
             "outcome": "committed",
             "new_epoch": new_epoch.get("epoch"),
             "participants": archive_new["challenge"]["participants"],
             "ranking": outcome.get("ranking"),
             "persisted": outcome.get("persisted"),
             "seats_after": list(archive_new["slots"].get("overall", ())),
             "exploration_after": list(
                 archive_new["slots"].get("exploration", ()))})
        return {"status": "ARCHIVE_COMMITTED", "archive": archive_new,
                "refresh": dict(outcome, status="committed",
                                exploration_after=list(
                                    archive_new["slots"].get("exploration", ())))}
    return _kept(str(outcome.get("status") or "refresh_rejected"),
                 str(outcome.get("note") or ""),
                 phase=outcome.get("phase"), missing=outcome.get("missing"),
                 extra=outcome)


#: 一个（身份 × 根）补根评估折算的桌数：2 臂 × 2 桌（group-dev-v1 完整小组阶段）。
#: 刷新补根预算按剩余 tables_full 折算成"可补根次数"（§9.2 不足预算保持原席）。
AV_TABLES_PER_ROOT_EVALUATION = 4.0


def _av_refresh_budget(ledger: Optional["ActionValueLedger"]) -> Optional[int]:
    """刷新补根预算（根·次）：把剩余 tables_full 折算成可补的根评估次数。

    未授权/未限额的账户返回 None（不假装知道余量）；不足一次即 0——调用方据此
    走 apply_challenge 的 budget_insufficient 分支（保持原席，挑战者留探索队列）。
    """

    if ledger is None:
        return None
    if ledger.authorized_total("tables_full") is None:
        return None
    remaining = ledger.remaining("tables_full")
    if remaining is None:
        return None
    return int(remaining // AV_TABLES_PER_ROOT_EVALUATION)



# ===========================================================================
# P7b（R7 修复）· 「补根 → 晋升」调度：把补齐缺失根接进状态机
#
# 缺陷（P7 收口报告 §4 第 2 条，Lead 确认为功能阻断）：A2 已把挑战事务化（原席 +
# 通道根集 + epoch 为事务基准，任一非 committed 结局保原席），但状态机一轮只评一个
# 候选，"补齐挑战点名的缺失根"没有调度入口 → 真实运行停在 pending_partial
# （REFRESH_PENDING），端到端晋升不可达、档案席位永不翻动。
#
# 本节语义纪律（与 A2/P6 逐条对齐）：
#   ① 提交条件不变：只有 apply_challenge 的 committed 分支换席/换 epoch；补根**只
#      补证据**（写候选条目的 normal_evaluations），绝不直接落席、绝不混新旧均值；
#   ② 评价通路不新开：补根复用 sitin_natural_panel.run_natural_panel（同一批次 7
#      授权门、同一合同、同一真实驱动、同一 Q4/Q7 根身份与整根失效判据）；
#   ③ 记账不绕开：先预留后执行（同一共享账本 ActionValueLedger）、失败照记、恢复先
#      对账；实例进 P6 的 instances.json 台账（先落盘后执行、已完成实例不覆盖）；
#      逐（身份 × 情景）检查点保证进程被杀后不重跑、不重复计费；
#   ④ 根身份 = (对手情景, panel_seed, 根序号)（Q7），与候选源码无关 → 同一根可对
#      另一身份**逐字复现同一牌山**，两身份因此在同一根上同根集可比（T12）；
#   ⑤ 新鲜性：只对"该身份在本面板上一根都没有"的面板补根——面板执行器按根前缀
#      复现（root01..rootN），若该身份已有较低序号根，补根会重跑它（重复评价同一
#      实例），故判为不可调度并如实记账（不猜、不重跑、不拿他人结果顶替）。
# ===========================================================================

#: 补根事务件 schema（读缺失 → 补根 → 重试提交，逐轮可核）。
AV_REFRESH_FILL_TX_SCHEMA = "sitin-av-refresh-fill/1"
#: 一次补根步骤内最多「补根 → 重试提交」的轮数（每轮都应有净进展；防死循环）。
AV_REFRESH_FILL_MAX_ROUNDS = 6
#: 补根终态（**保持原席原 epoch**）的停因词表：状态读得懂、批次报告可核对。
AV_REFRESH_FILL_KEEP_STOP_REASONS: Dict[str, str] = {
    "budget_insufficient": "refresh_budget_insufficient_old_seats_kept",
    "unauthorized": "refresh_unauthorized_old_seats_kept",
    "unschedulable": "refresh_unschedulable_old_seats_kept",
    "evidence_incomplete": "refresh_evidence_incomplete_old_seats_kept",
    "rounds_exhausted": "refresh_rounds_exhausted_old_seats_kept",
    "not_promoting": "refresh_not_promoting_old_seats_kept",
}


def _av_refresh_contract() -> Dict[str, Any]:
    """补根所用阶段合同（与自然面板步同一份 group-dev-v1，同一路径）。"""

    return json.loads((_project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
                       / "contracts/group-dev-v1.json")).read_text(encoding="utf-8"))


def _av_root_index_of(root_id: Any) -> Optional[int]:
    """根序号（Q7 根身份 np-{mix}-{seed}-rootNN 的 NN）；不可解析返回 None。"""

    match = re.search(r"-root(\d+)$", str(root_id or ""))
    return int(match.group(1)) if match else None


def _av_refresh_root_registry(run_root: Path) -> Dict[str, Any]:
    """**根复现登记表**：root_id → 复现参数（对手情景/panel_seed/根序号/座位数）。

    只从**落盘状态**读（迭代 plan 的自然面板配置 + 自然面板样本），不猜任何参数：
    缺登记即"无法安全复现该根"（调用方记不可调度、保原席）。同一 root_id 出现在
    多份状态里且参数不一致时记 conflicts（同 ID 不同内容属 Q7 违约，不静默取其一）。
    """

    registry: Dict[str, Dict[str, Any]] = {}
    conflicts: List[Dict[str, Any]] = []
    for root in _av_chain_run_roots(Path(run_root)):
        for iter_dir in _av_iteration_dirs_in(root):
            state_path = Path(iter_dir) / "state.json"
            if not state_path.is_file():
                continue
            try:
                other = av_state_load(state_path)
            except (OSError, ValueError):
                continue
            plan = other.get("plan") or {}
            for sample in ((other.get("natural_result") or {}).get("samples") or []):
                root_id = sample.get("source_root_id")
                if not isinstance(root_id, str) or not root_id:
                    continue
                index = sample.get("root_index")
                if index is None:
                    index = _av_root_index_of(root_id)
                row = {"root_id": root_id,
                       "opponent_mix": sample.get("opponent_mix"),
                       "root_index": (int(index) if index is not None else None),
                       "panel_seed": plan.get("panel_seed"),
                       "seats_per_root": plan.get("natural_seats"),
                       "iter_dir": str(iter_dir)}
                prior = registry.get(root_id)
                if prior is None:
                    registry[root_id] = row
                elif [prior[key] for key in ("opponent_mix", "root_index",
                                             "panel_seed", "seats_per_root")] != \
                        [row[key] for key in ("opponent_mix", "root_index",
                                              "panel_seed", "seats_per_root")]:
                    conflicts.append({"root_id": root_id, "kept": prior, "seen": row,
                                      "note": "同 ID 不同复现参数（Q7 违约）：不启用该根"})
                    registry.pop(root_id, None)
    return {"registry": registry, "conflicts": conflicts}


def _av_refresh_panel_key(registry: Mapping[str, Any], root_id: Any) -> Optional[Tuple[str, int]]:
    """根所属面板键 (对手情景, panel_seed)；未登记返回 None。"""

    row = registry.get(str(root_id))
    if not row or row.get("panel_seed") is None or not row.get("opponent_mix"):
        return None
    return (str(row["opponent_mix"]), int(row["panel_seed"]))


def _av_refresh_participant_source(state: Mapping[str, Any], run_root: Path,
                                   candidate_id: str) -> Optional[Dict[str, Any]]:
    """补根对象的候选源码：当前迭代在案源码 → 运行链上生成该身份的迭代产物。

    只接受**摘要自洽**的源码（在案 candidate_source_sha256 与源码逐字重算一致）：
    找不到就返回 None，调用方记不可调度并保原席——绝不猜源码、绝不冒名评价。
    """

    identity = state.get("identity") or {}
    if (str(identity.get("candidate_id")) == str(candidate_id)
            and state.get("candidate_source")):
        source = str(state["candidate_source"])
        recorded = identity.get("candidate_source_sha256")
        if recorded is not None and str(recorded) != sha256_text(source):
            return None
        return {"source": source, "sha256": sha256_text(source),
                "origin": "current_iteration", "iter_dir": state.get("iter_dir")}
    for root in _av_chain_run_roots(Path(run_root)):
        for iter_dir in reversed(_av_iteration_dirs_in(root)):
            state_path = Path(iter_dir) / "state.json"
            if not state_path.is_file():
                continue
            try:
                other = av_state_load(state_path)
            except (OSError, ValueError):
                continue
            if str((other.get("identity") or {}).get("candidate_id")) != str(candidate_id):
                continue
            source = other.get("candidate_source")
            if not source:
                continue
            digest = sha256_text(str(source))
            recorded = (other.get("identity") or {}).get("candidate_source_sha256")
            if recorded is not None and str(recorded) != digest:
                continue        # 在案摘要不符：不采用该产物（不猜）
            return {"source": str(source), "sha256": digest,
                    "origin": "chain_iteration", "iter_dir": str(iter_dir)}
    return None


def _av_refresh_fill_items(*, missing: Mapping[str, Any],
                           registry: Mapping[str, Any],
                           entries: Mapping[str, Any],
                           tables_per_group: int) -> Tuple[List[Dict[str, Any]],
                                                            List[Dict[str, Any]]]:
    """挑战点名的缺失根 → 可复现补根工作项（身份 × 情景 × 面板种子 × 根索引集）。

    每个工作项 = 一次 run_natural_panel(root_indices=[...])（P2b 显式根选取），
    因此**只评价缺失的那些根**：
      - 缺失根必须全部登记了复现参数，否则整组不可调度（不猜参数）；
      - 逐根新鲜性（防御）：该身份已持有证据的根不得进入选择集（同一实例不重复
        评价、不重复计费）——挑战给出的 missing 本身已排除既有根，此处再核一遍；
      - 同一 (情景, 面板种子) 的缺失根合成**一次**调用（选择集=集合，产物逐字节
        一致），避免同面板多次开面板。
    """

    items: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for cid in sorted(missing):
        held = set(((entries.get(cid) or {}).get("normal_evaluations") or {}).keys())
        panels: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for root_id in sorted(missing.get(cid) or []):
            row = registry.get(str(root_id))
            if (not row or row.get("panel_seed") is None
                    or row.get("seats_per_root") is None
                    or row.get("root_index") is None):
                blocked.append({"candidate_id": cid, "root_id": root_id,
                                "reason": "根未登记复现参数（不猜 panel_seed/座位数）"})
                continue
            key = (str(row["opponent_mix"]), int(row["panel_seed"]))
            slot = panels.setdefault(key, {"indexes": set(), "seats": set()})
            slot["indexes"].add(int(row["root_index"]))
            slot["seats"].add(int(row["seats_per_root"]))
        for (mix, seed), slot in sorted(panels.items()):
            if len(slot["seats"]) != 1:
                blocked.append({"candidate_id": cid, "opponent_mix": mix,
                                "panel_seed": seed,
                                "reason": "同面板根的座位数不一致：{0}".format(
                                    sorted(slot["seats"]))})
                continue
            seats = int(next(iter(slot["seats"])))
            held_indexes = {int(registry[rid]["root_index"]) for rid in held
                            if _av_refresh_panel_key(registry, rid) == (mix, seed)}
            stale = sorted(slot["indexes"] & held_indexes)
            if stale:
                # 防御：档案里已有这些根（挑战不应把它们算作缺失）→ 不重复评价。
                blocked.append({
                    "candidate_id": cid, "opponent_mix": mix, "panel_seed": seed,
                    "reason": ("该身份已持有根索引 {0} 的证据：不重复评价同一实例"
                               "（这些根不进入选择集）".format(stale))})
            selected = sorted(slot["indexes"] - held_indexes)
            if not selected:
                continue
            items.append({
                "candidate_id": cid, "opponent_mix": mix, "panel_seed": seed,
                "root_indexes": selected,
                "root_ids": [av_natural_panel().natural_root_id(mix, seed, index)
                             for index in selected],
                "seats_per_root": seats,
                # 费用按**被选根**计（只评缺失的根，不跑整前缀）。
                "planned_tables": float(len(selected) * seats * 2
                                        * int(tables_per_group)),
                "missing_roots": len(slot["indexes"])})
    return items, blocked


def _av_refresh_expected_instances(item: Mapping[str, Any],
                                   tables_per_group: int) -> List[Dict[str, Any]]:
    """补根实例清单（身份 × 根 × 座位 × 臂 × 赛程）——真实副作用**之前**即可落盘。"""

    schedule = "stage_complete:{0}_tables".format(int(tables_per_group))
    natural = av_natural_panel()
    seed = int(item["panel_seed"])
    seed_of = getattr(natural, "natural_root_seed", None)
    rows: List[Dict[str, Any]] = []
    for index in [int(value) for value in item["root_indexes"]]:
        root_id = natural.natural_root_id(str(item["opponent_mix"]), seed, index)
        root_seed = (int(seed_of(seed, str(item["opponent_mix"]), index))
                     if seed_of else None)
        for seat in range(int(item["seats_per_root"])):
            for arm in AV_INSTANCE_ARMS:
                rows.append(av_instance_row(
                    candidate_id=item["candidate_id"],
                    opponent_mix=item["opponent_mix"], panel_seed=seed,
                    source_root_id=root_id, root_index=index, root_seed=root_seed,
                    seat=seat, arm=arm, schedule=schedule,
                    participant_id=item["candidate_id"],
                    planned_tables=int(tables_per_group)))
    return rows


def _av_refresh_panel_matches(panel: Mapping[str, Any], *, item: Mapping[str, Any],
                              source: Mapping[str, Any]) -> Tuple[bool, str]:
    """补根结果对账判据：盘上面板确实是**本次身份 × 本面板 × 本选择集**的结果。"""

    identity = panel.get("identity") or {}
    config = panel.get("config") or {}
    if str(identity.get("opponent_mix")) != str(item["opponent_mix"]):
        return False, "对手情景不符"
    if int(identity.get("panel_seed") or -1) != int(item["panel_seed"]):
        return False, "面板种子不符"
    if int(config.get("roots") or 0) != len(item["root_indexes"]):
        return False, "选择集长度不符（config.roots 与 root_indices 不一致）"
    if int(config.get("seats_per_root") or 0) != int(item["seats_per_root"]):
        return False, "座位数不符"
    if str(identity.get("candidate_source_sha256")) != str(source.get("sha256")):
        return False, "候选源码摘要不符（不采用他者结果）"
    produced = {str(sample.get("source_root_id"))
                for sample in (panel.get("samples") or [])}
    wanted = {str(root_id) for root_id in item["root_ids"]}
    if produced != wanted:
        return False, "根清单不符（多 {0} / 缺 {1}）".format(
            sorted(produced - wanted), sorted(wanted - produced))
    indexes = sorted(int(sample.get("root_index") or 0)
                     for sample in (panel.get("samples") or []))
    if indexes != sorted(int(value) for value in item["root_indexes"]):
        return False, "根索引不符（{0} != {1}）".format(
            indexes, sorted(int(value) for value in item["root_indexes"]))
    return True, ""


def _av_refresh_run_panel(state: Dict[str, Any], run_root: Path,
                          ledger: "ActionValueLedger",
                          authorization: Optional[Mapping[str, Any]],
                          item: Mapping[str, Any], source: Mapping[str, Any],
                          tables_per_group: int) -> Dict[str, Any]:
    """执行/复用**一个**补根面板（身份 × 对手情景 × 面板种子 × 根索引选择集）。

    事务顺序与自然面板步**同源**（S3）：检查点复用 → 盘上结果对账采用 → 新尝试
    （先落实例"已开始"→ 预留 → 执行 → 结算 → 完成检查点）；任何一步中断都可由下一次
    调用按同一顺序复原：不重跑、不重复计费、不拿他人结果顶替。
    """

    iter_dir = Path(state["iter_dir"])
    candidate_id = str(item["candidate_id"])
    mix = str(item["opponent_mix"])
    cid12 = candidate_id[:12]
    key = "{0}-{1}".format(cid12, mix)
    panel_dir = iter_dir / "refresh" / key
    panel_path = panel_dir / "panel.json"
    checkpoint_name = "refresh-" + key
    step_prefix = "refresh:{0}:{1}:".format(cid12, mix)
    indexes = [int(value) for value in item["root_indexes"]]
    # 账本步标识带**选择集记号**（与面板自身的记号同源）：只补缺失根的补根是不同
    # 任务身份，不能被该面板前缀账行的结算（TaskAlreadySettled）挡住。
    step_id = "{0}{1}".format(step_prefix,
                              av_natural_panel().natural_selection_token(indexes))
    checkpoint = av_checkpoint_load(iter_dir, checkpoint_name)
    previous_attempt = int((checkpoint or {}).get("attempt_no") or 0)
    attempt_no = max(1, previous_attempt)
    rows = av_ledger_rows_for_step(ledger, step_prefix=step_prefix,
                                   account="tables_full")
    expected = _av_refresh_expected_instances(item, tables_per_group)
    record: Dict[str, Any] = {
        "candidate_id": candidate_id, "opponent_mix": mix,
        "panel_seed": int(item["panel_seed"]), "root_ids": list(item["root_ids"]),
        "root_indexes": list(indexes),
        "seats_per_root": int(item["seats_per_root"]),
        "step_id": step_id, "planned_tables": float(item["planned_tables"]),
        "source": {"origin": source.get("origin"), "sha256": source.get("sha256")}}
    panel: Optional[Mapping[str, Any]] = None
    reuse: Optional[str] = None
    if av_checkpoint_result_matches(checkpoint, panel_path):
        # 检查点 completed 且不可变结果摘要一致：直接复用（不重跑、不重复计费）。
        panel = json.loads(panel_path.read_text(encoding="utf-8"))
        reuse = "checkpoint"
    elif panel_path.is_file() and rows:
        adopted: Optional[Mapping[str, Any]] = None
        try:
            adopted = json.loads(panel_path.read_text(encoding="utf-8"))
        except ValueError:
            adopted = None
        if isinstance(adopted, Mapping):
            matched, why = _av_refresh_panel_matches(adopted, item=item, source=source)
            if matched:
                executed = int((adopted.get("cost") or {}).get(
                    "tables_full_executed") or 0)
                record["reconcile"] = av_reconcile_ledger_attempts(
                    ledger, step_prefix=step_prefix, account="tables_full",
                    result_available=True, executed=float(executed),
                    reason="补根 {0}/{1}（结果在盘上，采用并结算）".format(cid12, mix))
                panel = adopted
                reuse = "reconciled_result_on_disk"
            else:
                record["reconcile_note"] = why
    if panel is None:
        attempt_no = previous_attempt + 1
        record["reconcile"] = av_reconcile_ledger_attempts(
            ledger, step_prefix=step_prefix, account="tables_full",
            reason="补根 {0}/{1}（旧尝试让位，失败成本保留）".format(cid12, mix))
        av_instances_apply(iter_dir,
                           updates=[dict(row, status="started") for row in expected],
                           attempt_no=attempt_no,
                           iteration_no=int(state.get("iteration_no") or 0),
                           run_id=str(state.get("run_id") or ""),
                           mirror_root=run_root)
        av_checkpoint_write(iter_dir, checkpoint_name, {
            "status": "started", "step": "REFRESH_PENDING", "mix": mix,
            "candidate_id": candidate_id, "attempt_no": attempt_no,
            "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
            "step_id": step_id, "cost_planned": float(item["planned_tables"]),
            "cost_charged": None,
            "instance_keys": [row["instance_key"] for row in expected],
            "started_at_utc": utc_now()})
        try:
            reservation = ledger.reserve(
                step_id=step_id, account="tables_full",
                amount=float(item["planned_tables"]),
                note=("补根：身份 {0} × 情景 {1} × 面板种子 {2} × 根索引 {3}"
                      "（{4} 座位 × 2 臂 × {5} 桌）").format(
                          cid12, mix, int(item["panel_seed"]), indexes,
                          int(item["seats_per_root"]), int(tables_per_group)))
        except (LedgerUnauthorized, LedgerOverAuthorized, BudgetExhausted) as error:
            record.update({"status": "budget_insufficient",
                           "reason": "补根预算/记账拒绝（早于费用）：{0}".format(error)})
            _av_refresh_abort(run_root, ledger, expected, step_prefix=step_prefix,
                              attempt_no=attempt_no, reason=record["reason"],
                              iteration_no=int(state.get("iteration_no") or 0),
                              run_id=str(state.get("run_id") or ""),
                              iter_dir=iter_dir)
            return {"attempt": record, "panel": None, "reason": record["reason"]}
        av_fault_point("refresh:{0}:{1}:after_reserve".format(cid12, mix),
                       step_id=step_id)
        try:
            panel = av_natural_panel().run_natural_panel(
                candidate_source=str(source["source"]), opponent=mix,
                root_indices=list(indexes),
                seats_per_root=int(item["seats_per_root"]),
                contract=_av_refresh_contract(), out_dir=panel_dir,
                authorization=authorization, panel_seed=int(item["panel_seed"]),
                ledger_path=None)
        except SystemExit as error:
            record.update({"status": "unauthorized",
                           "reason": "补根授权缺口：{0}".format(error)})
            _av_refresh_abort(run_root, ledger, expected, step_prefix=step_prefix,
                              attempt_no=attempt_no, reason=record["reason"],
                              iteration_no=int(state.get("iteration_no") or 0),
                              run_id=str(state.get("run_id") or ""),
                              iter_dir=iter_dir)
            return {"attempt": record, "panel": None, "reason": record["reason"]}
        except (BudgetExhausted, LedgerUnauthorized, LedgerOverAuthorized) as error:
            record.update({"status": "budget_insufficient",
                           "reason": "补根预算耗尽：{0}".format(error)})
            _av_refresh_abort(run_root, ledger, expected, step_prefix=step_prefix,
                              attempt_no=attempt_no, reason=record["reason"],
                              iteration_no=int(state.get("iteration_no") or 0),
                              run_id=str(state.get("run_id") or ""),
                              iter_dir=iter_dir)
            return {"attempt": record, "panel": None, "reason": record["reason"]}
        except Exception as error:  # 执行器级异常：面板未产出（费用保守结算，不静默吞）
            record.update({"status": "failed",
                           "reason": "补根执行异常（{0}）：{1}".format(
                               type(error).__name__, error)})
            _av_refresh_abort(run_root, ledger, expected, step_prefix=step_prefix,
                              attempt_no=attempt_no, reason=record["reason"],
                              iteration_no=int(state.get("iteration_no") or 0),
                              run_id=str(state.get("run_id") or ""),
                              iter_dir=iter_dir)
            return {"attempt": record, "panel": None, "reason": record["reason"]}
        av_fault_point("refresh:{0}:{1}:after_result_before_settle".format(cid12, mix),
                       step_id=step_id)
        executed = int((panel.get("cost") or {}).get("tables_full_executed") or 0)
        ledger.settle(reservation, actual=float(executed),
                      note="补根实跑桌赛实例 {0}/{1}（失败桌照记）".format(
                          executed, int(item["planned_tables"])))
        av_fault_point("refresh:{0}:{1}:after_settle_before_completion".format(cid12, mix),
                       step_id=step_id)
    if not isinstance(panel, Mapping):
        record.update({"status": "failed", "reason": "补根结果不是映射"})
        return {"attempt": record, "panel": None, "reason": record["reason"]}
    executed = int((panel.get("cost") or {}).get("tables_full_executed") or 0)
    # 身份投影统一（与自然面板步同源）：面板按直接计算 id 报身份，编排用 S4 强化绑定
    # id；原始 id 保留在 panel_reported_candidate_id 供审计（不改数值证据）。
    for sample in panel.get("samples") or []:
        sample["panel_reported_candidate_id"] = sample.get("candidate_id")
        sample["candidate_id"] = candidate_id
        for arm in (sample.get("arms") or {}).values():
            if arm.get("candidate_id") not in (None, AV_BASELINE_ID):
                arm["candidate_id"] = candidate_id
    instance_report = av_instances_apply(
        iter_dir,
        updates=_av_natural_result_instances(panel, expected, mix=mix,
                                            result_path=panel_path),
        attempt_no=attempt_no, iteration_no=int(state.get("iteration_no") or 0),
        run_id=str(state.get("run_id") or ""), mirror_root=run_root)
    av_checkpoint_write(iter_dir, checkpoint_name, {
        "status": "completed", "step": "REFRESH_PENDING", "mix": mix,
        "candidate_id": candidate_id, "attempt_no": attempt_no,
        "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
        "step_id": step_id, "cost_planned": float(item["planned_tables"]),
        "cost_charged": executed, "result_path": str(panel_path),
        "result_sha256": _av_file_digest(panel_path),
        "instance_keys": [row["instance_key"] for row in expected],
        "reused_from": reuse, "instances": instance_report,
        "completed_at_utc": utc_now()})
    record.update({"status": "completed", "reuse": reuse, "attempt_no": attempt_no,
                   "tables_executed": executed, "panel_path": str(panel_path)})
    return {"attempt": record, "panel": panel, "instances": instance_report}


def _av_refresh_abort(run_root: Path, ledger: "ActionValueLedger",
                      expected: Sequence[Mapping[str, Any]], *,
                      step_prefix: str, attempt_no: int, reason: str,
                      iteration_no: int = 0, run_id: str = "",
                      iter_dir: Optional[Path] = None) -> None:
    """补根失败收尾：在途预留**保守结算**（失败成本保留），实例记 aborted。

    A3：实例落**迭代台账**（iter_dir/instances.json），运行级台账只作累计镜像。
    """

    av_reconcile_ledger_attempts(ledger, step_prefix=step_prefix,
                                 account="tables_full",
                                 reason="补根失败（{0}）".format(reason))
    av_instances_apply(Path(iter_dir) if iter_dir is not None else run_root,
                       updates=[dict(row, status="aborted", reason=reason)
                                for row in expected],
                       attempt_no=attempt_no, iteration_no=iteration_no,
                       run_id=run_id,
                       mirror_root=(run_root if iter_dir is not None else None))



def _av_refresh_merge_fills(state: Mapping[str, Any], run_root: Path,
                            fills: Mapping[str, Any]) -> Dict[str, Any]:
    """把补根样本按**完整根身份增量合并**进对应身份的档案条目（A3 同一合并器）。

    只写 entries（证据），绝不动 slots/epoch——换席仍只由 apply_challenge 的
    committed 分支决定（提交条件不变，不混新旧均值）。
    """

    archive_mod = av_archive()
    archive_path = Path(run_root) / "archive" / "av-archive.json"
    archive = _av_previous_archive(state, run_root)
    entries = dict(archive.get("entries") or {})
    report: Dict[str, Any] = {}
    for candidate_id, payload in sorted(fills.items()):
        item, result = payload
        panel = result.get("panel") or {}
        samples = list(panel.get("samples") or [])
        merged = archive_mod.merge_archive_entry(entries.get(candidate_id),
                                                 candidate_id, samples, safety="PASS")
        entries[candidate_id] = merged
        report[candidate_id] = {
            "roots_added": sorted((merged.get("evidence_merge") or {}).get("added") or []),
            "n_samples": len(samples),
            "panel_seed": item.get("panel_seed"),
            "opponent_mix": item.get("opponent_mix")}
    archive["entries"] = entries
    av_atomic_write_json(archive_path, archive)
    return report


def _av_refresh_fill_tx(state: Mapping[str, Any], rounds: Sequence[Mapping[str, Any]],
                        verdict: Mapping[str, Any], seats_before: Sequence[str],
                        seats_after: Sequence[str]) -> Path:
    """补根事务件：逐轮 missing/预算/执行与最终结局、席位前后快照一次落盘。"""

    return _av_tx_write(Path(state["iter_dir"]), "refresh_fill", {
        "schema": AV_REFRESH_FILL_TX_SCHEMA,
        "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
        "candidate_id": (state.get("identity") or {}).get("candidate_id"),
        "seats_before": list(seats_before), "seats_after": list(seats_after),
        "rounds": [dict(row) for row in rounds], "outcome": dict(verdict)})


def _av_refresh_keep_reason(rounds: Sequence[Mapping[str, Any]], *,
                            token_ok: bool, refresh_status: str) -> str:
    """补根保席的**停因**：把"未授权/预算不足/不可复现/证据仍不全"分开记，不混谈。"""

    last = dict(rounds[-1]) if rounds else {}
    if not token_ok and last.get("missing"):
        return "unauthorized"
    if refresh_status == "budget_insufficient":
        return "budget_insufficient"
    if refresh_status not in ("pending_partial", ""):
        return "not_promoting"
    if (len(rounds) >= AV_REFRESH_FILL_MAX_ROUNDS and last.get("filled")
            and refresh_status == "pending_partial"):
        return "rounds_exhausted"
    if last.get("skipped"):
        return "budget_insufficient"
    if any(row.get("filled") for row in rounds):
        return "evidence_incomplete"
    if last.get("blocked"):
        return "unschedulable"
    return "unschedulable"


def _step_refresh_fill(state: Dict[str, Any], run_root: Path,
                       ledger: "ActionValueLedger",
                       authorization: Optional[Mapping[str, Any]],
                       test_runtime_factory: Optional[
                           Callable[[], Mapping[str, Any]]] = None
                       ) -> Dict[str, Any]:
    """REFRESH_PENDING 的调度入口：按剩余预算补根 → 重试提交，直到换席或明确保席。

    P7c：除 normal 通道外，**家族通道**的补根在同一入口内调度（声明批物化 +
    点名缺失根），两通道各自独立保原席原 epoch（停因分开记）。

    每轮都由**挑战自己的 missing**驱动（不自行扩大评价面）：
      ① 走同一条提交路径 _av_commit_archive 取权威结局（committed / pending 的
         missing / 其它保席结局）；
      ② pending：把 missing 映射成可复现工作项（身份 × 情景 × 面板种子 × 根前缀），
         按剩余 tables_full 与根·次预算执行（检查点复用、实例台账、先预留后执行）；
      ③ 只合并证据（entries）后重试提交；有净进展才进入下一轮。

    终态可读：committed → 换席换 epoch（停因 refresh_committed_new_epoch）；
    否则一律保持原席原 epoch 并写明确停因（预算不足/未授权/不可复现/证据不全）。
    幂等：本步骤可被反复调用（进程被杀后恢复走同一入口），已完成的（身份 × 情景）
    面板经检查点复用，不重跑、不重复计费。
    """

    iter_dir = Path(state["iter_dir"])
    fill = state.setdefault("refresh_fill", {"schema": AV_REFRESH_FILL_TX_SCHEMA,
                                             "attempts": []})
    fill["schema"] = AV_REFRESH_FILL_TX_SCHEMA
    fill.setdefault("attempts", [])
    # —— Q6：统一受信授权校验（补根 = 真实桌赛；未通过即不动一张桌）——
    token_ok, auth_refusal, auth_audit = av_authorization_allows(
        authorization, operation="conditional_refill",
        required=AV_AUTHORIZATION_OPERATION_REQUIREMENTS["conditional_refill"])
    fill["authorization"] = auth_audit
    state["authorization"] = auth_audit
    archive_before = _av_previous_archive(state, run_root)
    seats_before = list(((archive_before.get("slots") or {}).get("overall")) or [])
    rounds: List[Dict[str, Any]] = []
    outcome = _av_commit_archive(state, run_root, attempt_refresh=True,
                                 refresh_budget=_av_refresh_budget(ledger))
    for round_no in range(1, AV_REFRESH_FILL_MAX_ROUNDS + 1):
        refresh = outcome.get("refresh") if isinstance(outcome.get("refresh"),
                                                       Mapping) else {}
        refresh_status = str(refresh.get("status") or "")
        missing = dict(refresh.get("missing") or {})
        row: Dict[str, Any] = {
            "round": round_no, "refresh_status": refresh_status, "missing": missing,
            "filled": [], "blocked": [], "skipped": [],
            "budget_refresh_evaluations": _av_refresh_budget(ledger),
            "remaining_tables_full": (ledger.remaining("tables_full")
                                      if ledger is not None else None)}
        rounds.append(row)
        if refresh_status != "pending_partial" or not missing:
            break
        if not token_ok:
            row["note"] = ("补根是真实桌赛：需要**受信**授权（Q6 统一校验未通过："
                           "{0}）；未取得即不动一张桌").format(auth_refusal)
            break
        archive = _av_previous_archive(state, run_root)
        entries = dict(archive.get("entries") or {})
        registry = _av_refresh_root_registry(run_root)
        tables_per_group = int(_av_refresh_contract()["group"]["tables_per_group"])
        items, blocked = _av_refresh_fill_items(
            missing=missing, registry=registry["registry"], entries=entries,
            tables_per_group=tables_per_group)
        row["blocked"] = list(blocked) + list(registry["conflicts"])
        if not items:
            break
        progressed = False
        for item in items:
            source = _av_refresh_participant_source(state, run_root,
                                                    str(item["candidate_id"]))
            if source is None:
                row["blocked"].append(dict(item, reason=(
                    "候选源码不可得（在案摘要不符或无生成产物）：不猜源码、不冒名评价")))
                continue
            budget = _av_refresh_budget(ledger)
            remaining = (ledger.remaining("tables_full")
                         if ledger is not None else None)
            if budget is not None and len(item["root_ids"]) > int(budget):
                row["skipped"].append(dict(item, reason="补根预算不足（根·次）",
                                           budget=budget))
                continue
            if remaining is not None and float(item["planned_tables"]) > float(remaining):
                row["skipped"].append(dict(item, reason="剩余 tables_full 不足",
                                           remaining=remaining))
                continue
            result = _av_refresh_run_panel(state, run_root, ledger, authorization,
                                           item, source, tables_per_group)
            fill["attempts"].append(result["attempt"])
            if result.get("panel") is None:
                row["skipped"].append({"candidate_id": item["candidate_id"],
                                       "opponent_mix": item["opponent_mix"],
                                       "panel_seed": item["panel_seed"],
                                       "reason": result.get("reason")})
                continue
            merged = _av_refresh_merge_fills(state, run_root,
                                             {str(item["candidate_id"]): (item, result)})
            added = list((merged.get(str(item["candidate_id"])) or {}).get(
                "roots_added") or [])
            row["filled"].append({
                "candidate_id": item["candidate_id"],
                "opponent_mix": item["opponent_mix"],
                "panel_seed": item["panel_seed"], "roots": list(item["root_ids"]),
                "root_indexes": list(item["root_indexes"]),
                "reuse": result["attempt"].get("reuse"),
                "tables_executed": result["attempt"].get("tables_executed"),
                "roots_added": added,
                "merge": merged.get(str(item["candidate_id"]))})
            # 净进展 = **真的补进根证据**；面板跑了但整根失效（臂失败）不算进展，
            # 否则会在同一 missing 上空转（重复调用、假装推进）。
            progressed = progressed or bool(added)
        if not progressed:
            break
        outcome = _av_commit_archive(state, run_root, attempt_refresh=True,
                                     refresh_budget=_av_refresh_budget(ledger))
    refresh = outcome.get("refresh") if isinstance(outcome.get("refresh"), Mapping) else {}
    refresh_status = str(refresh.get("status") or "")
    archive_after = _av_previous_archive(state, run_root)
    seats_after = list(((archive_after.get("slots") or {}).get("overall")) or [])
    archive_path = str(Path(run_root) / "archive" / "av-archive.json")
    if refresh_status == "committed":
        verdict = {"status": "committed", "refresh_status": refresh_status,
                   "epoch_after": refresh.get("epoch_after"),
                   "seats_after": seats_after,
                   "stop_reason": "refresh_committed_new_epoch",
                   "note": ("全员在旧根+新根齐备 → 原子提交新 epoch 并统一重排"
                            "（补根只补证据，换席仍只由 apply_challenge 提交分支决定）")}
        fill["outcome"] = verdict
        state["stop_reason"] = "refresh_committed_new_epoch"
        state["identity"]["panel_epoch"] = "normal@epoch-committed"
        state["archive"] = {"archive_path": archive_path,
                            "refresh_status": "committed", "seats_kept": False}
        # —— P7c：normal 通道已提交后，家族通道在自己的补根循环里收口 ——
        family_verdict = (_av_family_fill(state, run_root, ledger, authorization,
                                          test_runtime_factory)
                          if _av_family_declared_channel(state) else None)
        if family_verdict is not None:
            verdict["family_refresh"] = {"status": family_verdict.get("status"),
                                         "stop_reason": family_verdict.get("stop_reason")}
            if family_verdict.get("status") != "committed":
                # 家族通道未齐备：整体停因记家族通道（normal 的换席结果已落盘）。
                state["stop_reason"] = family_verdict["stop_reason"]
        _av_refresh_fill_tx(state, rounds, verdict, seats_before, seats_after)
        if (family_verdict or {}).get("terminal") == "INPUT_GAP":
            # P16-C5：家族冻结件不可用 ⇒ 迭代级具名停止（不继续推进、不提交）。
            av_state_history_append(
                state, "INPUT_GAP",
                "家族通道具名停止：冻结核心根清单不可用（保留原件，不重定需求集合）",
                family_stop_reason=family_verdict.get("stop_reason"),
                seats_after=seats_after)
            return {"advanced": "INPUT_GAP"}
        av_state_history_append(state, "ARCHIVE_COMMITTED",
                                "补根齐备 → 原子提交新 epoch（席位按新根集重排）",
                                refresh="committed", seats_after=seats_after,
                                family=(family_verdict or {}).get("status"))
        return {"advanced": "ARCHIVE_COMMITTED"}
    keep = _av_refresh_keep_reason(rounds, token_ok=token_ok,
                                   refresh_status=refresh_status)
    stop_reason = AV_REFRESH_FILL_KEEP_STOP_REASONS[keep]
    verdict = {"status": keep, "refresh_status": refresh_status,
               "missing": dict(refresh.get("missing") or {}),
               "seats_after": seats_after, "stop_reason": stop_reason,
               "note": ("补根未齐备：保持原席与原 epoch（不混新旧均值），挑战者留候选池"
                        "与探索队列；停因见 status")}
    fill["outcome"] = verdict
    fill["missing"] = dict(refresh.get("missing") or {})
    fill["next_step"] = ("下一轮迭代/推进按 next_generation_plan 重排；被保席的挑战者"
                         "仍在候选池，可在后续迭代重新挑战")
    state["stop_reason"] = stop_reason
    state["archive"] = {"archive_path": archive_path,
                        "refresh_status": refresh_status,
                        "epoch_kept": refresh.get("epoch_kept"), "seats_kept": True}
    state["identity"]["panel_epoch"] = "normal@epoch-kept(原席保留)"
    # —— P7c：家族通道在自己的补根循环里收口（两通道各自保原席原 epoch）——
    family_verdict = (_av_family_fill(state, run_root, ledger, authorization,
                                      test_runtime_factory)
                      if _av_family_declared_channel(state) else None)
    if family_verdict is not None:
        verdict["family_refresh"] = {"status": family_verdict.get("status"),
                                     "stop_reason": family_verdict.get("stop_reason")}
        state["stop_reason"] = (AV_FAMILY_COMMITTED_STOP_REASON
                                if family_verdict.get("status") == "committed"
                                else family_verdict["stop_reason"])
        state["archive"] = dict(state["archive"],
                                family_refresh_status=(family_verdict.get("refresh_status")
                                                       or family_verdict.get("status")),
                                family_epoch_kept=family_verdict.get("epoch_kept"))
    _av_refresh_fill_tx(state, rounds, verdict, seats_before, seats_after)
    if (family_verdict or {}).get("terminal") == "INPUT_GAP":
        av_state_history_append(
            state, "INPUT_GAP",
            "家族通道具名停止：冻结核心根清单不可用（保留原件，不重定需求集合）",
            family_stop_reason=family_verdict.get("stop_reason"),
            seats_after=seats_after)
        return {"advanced": "INPUT_GAP"}
    av_state_history_append(state, "ARCHIVE_COMMITTED",
                            "补根未齐备：保持原席原 epoch（{0}）".format(keep),
                            refresh=refresh_status, seats_kept=True,
                            family=(family_verdict or {}).get("status"))
    return {"advanced": "ARCHIVE_COMMITTED"}


# ===========================================================================
# P7c（R7 修复）· 家族/专长通道接线：家族根登记 + 条件评价层 + 家族 epoch/挑战
#
# 缺陷（P7b 收口报告 §5 实测结论，复审 §4 A3 未闭合）：
#   ① 家族席只在**首次提交**时定一次（_av_commit_archive 只在 epoch is None 分支写
#      pool_view 的席位），此后永不翻动；
#   ② 家族通道没有 epoch、也没有挑战接线（build_channel_epoch 只对 "normal" 调用）；
#   ③ 一轮只评一个谓词 → 同一候选要凑齐「该族机会/代价两侧」必须**跨迭代补评价**，
#      而这条路径没有调度入口 → 专长四席在实践中恒空。
#
# 本节把三块补齐，且**不新开第二条通路**（与 A2/P7b 逐条同源）：
#   ① 家族根登记（与 overall 同构）：archive/family-roots.json 按通道累积
#      {子场景 × 对手情景 × 根身份 → 复现参数}，跨运行链继承，冲突即不启用；
#   ② 条件评价层：家族证据按**完整根身份增量合并**（同一 merge_archive_entry），
#      H/M 两情景用情景限定格键共存（家族根身份不含情景，是两个真实实例）；
#   ③ 家族 epoch/挑战：build_channel_epoch(channel, …) + apply_challenge(channel, …)
#      与 normal 通道**同一套事务语义**（原席 + 根集 + epoch 作基准、只补证据不换席、
#      补根成功才提交、失败/预算不足保原席）；补根复用同一共享账本、P6 实例台账、
#      检查点复用、身份核验与 P7b 的停因词表。
#
# 接线边界（如实声明）：家族通道**按开轮显式声明启用**（plan.family_channel /
# plan.family_refresh）；未声明即零家族评价、零行为变化（既有运行逐字不变）。
# ===========================================================================

#: 家族两个子场景侧（§7.3：机会 open / 代价 cost）。
AV_FAMILY_SIDES: Tuple[str, ...] = ("open", "cost")
#: 一次家族条件评价的桌数口径（§5.3：2 臂 × 2 桌；与 run_av_evaluation 的
#: tables_full 预留恰好一致，账目无需另立换算）。
AV_TABLES_PER_FAMILY_EVALUATION = 4.0
#: 家族每受影响子场景的刷新根配额（§9.2：每子场景 4 根、H/M 各 2）。
AV_FAMILY_REFRESH_ROOTS_PER_SIDE = 4
#: 家族根台账 schema（archive/family-roots.json；与 overall 的 normal-roots 同构）。
#: R9/A2 起 /2：行里带**完整根身份**（生成器 × 子场景 × 情景 × 实际种子 × 根索引）
#: 与派生记号；/1 的行（裸根名 + 家族命名空间种子）不再被继承。
AV_FAMILY_ROOTS_SCHEMA = "sitin-av-family-roots/2"
#: 旧台账 schema 记号（只用于**显式**拒绝继承，不静默按新身份续写）。
AV_FAMILY_ROOTS_SCHEMA_LEGACY = "sitin-av-family-roots/1"
#: 家族 epoch 表 schema（archive/family-epochs.json：每通道一份，与 normal-epoch 同构）。
AV_FAMILY_EPOCHS_SCHEMA = "sitin-av-family-epochs/2"
#: 旧 epoch schema 记号（显式拒绝继承：旧根身份与新身份不可比）。
AV_FAMILY_EPOCHS_SCHEMA_LEGACY = "sitin-av-family-epochs/1"
#: 家族补根事务件 schema（读缺失 → 补根/物化声明 → 重试提交，逐轮可核）。
AV_FAMILY_FILL_TX_SCHEMA = "sitin-av-family-fill/1"
#: 家族通道提交时的停因记号（与 normal 的 refresh_committed_new_epoch 并列）。
AV_FAMILY_COMMITTED_STOP_REASON = "family_refresh_committed_new_epoch"
#: 家族通道**首次初始化**成功的停因记号（A1：无 epoch → 核心格补齐 → 建 epoch 1 +
#: 首个家族席；与"换 epoch"分开记，报告里能区分"首次建立"与"挑战翻动"）。
AV_FAMILY_ESTABLISHED_STOP_REASON = "family_first_seat_established_new_epoch"
#: 家族通道保原席原 epoch 的停因词表（与 P7b 同构，状态读得懂、批次报告可核）。
AV_FAMILY_KEEP_STOP_REASONS: Dict[str, str] = {
    "budget_insufficient": "family_refresh_budget_insufficient_old_seats_kept",
    "unauthorized": "family_refresh_unauthorized_old_seats_kept",
    "unschedulable": "family_refresh_unschedulable_old_seats_kept",
    "evidence_incomplete": "family_refresh_evidence_incomplete_old_seats_kept",
    "rounds_exhausted": "family_refresh_rounds_exhausted_old_seats_kept",
    "not_promoting": "family_refresh_not_promoting_old_seats_kept",
    "batch_invalid": "family_refresh_batch_invalid_old_seats_kept",
    # R9/A1：冲突声明或历史根身份混排 → 先处理身份，不换席也不换 epoch。
    "identity_conflict": "family_refresh_identity_conflict_old_seats_kept",
    # R9/P8：同一根连续 K 轮无进展 → 停止重试（具名停因，仍保原席原 epoch）。
    "family_refill_no_progress":
        "family_refill_no_progress_old_seats_kept",
    # R9/P9：声明解析（有界独立根搜索）在预算门内凑不齐**可见证**的根 ⇒ 具名停因，
    # 仍保原席原 epoch：配额不放宽、不拿不见证的根顶数。
    "declaration_unfillable":
        "family_refresh_declaration_unfillable_old_seats_kept",
}
#: P8（Lead 追加）：**同一根**连续多少轮「被评价而无任何新证据」即停止重试该根。
#:
#: 为什么是 2：家族单根面板的样本可用性由**前缀是否见证该谓词**决定，而前缀由冻结的
#: 根身份（生成器 × 子场景 × 对手情景 × 面板种子 × 根序号）**确定性复现**——同一根再
#: 评一次只会得到同一座牌山、同一前缀、同一见证结果。K=2 保留**一次**重试，足以吸收
#: 非确定性失败面（进程被杀、预算中断、执行器拒绝、账本冲突）在下一轮产出新证据的情
#: 形；第 2 次仍无进展即证明该根在当前冻结参数下产不出证据，继续重试到
#: AV_REFRESH_FILL_MAX_ROUNDS 只是把同样的钱花 6 遍（run2 的 attempt_no=8 怪账）。
AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS = 2
#: 家族晋升评价成本登记表（P7b §5.3 口径，**代码常数显式表达**：重验收批次据此
#: 按预算核算；逐项都可由 roots × tables_per_evaluation 复算，不写估读值）。
AV_FAMILY_PROMOTION_COST: Dict[str, Any] = {
    "tables_per_evaluation": AV_TABLES_PER_FAMILY_EVALUATION,
    "refresh_roots_per_side": AV_FAMILY_REFRESH_ROOTS_PER_SIDE,
    "seat_complete_roots": 8,               # 两侧各 4 根（H/M 各 2）
    "seat_complete_tables": 32,             # 8 根 × 4 桌：单候选一侧齐备
    "cross_iteration_side_fill_roots": 4,   # 跨迭代补另一侧的最小增量
    "cross_iteration_side_fill_tables": 16,
    "phase1_roots_cap": 8,                  # 挑战者补通道当前根（epoch 根集上界）
    "phase1_tables": 32,
    "phase2_roots": 2 * 8,                  # 刷新批 4+4 根 × 2 参与者（原席者+挑战者）
    "phase2_tables": 64,
    "promotion_cap_tables": 96,             # 一次家族晋升合计上界（32 + 64）
    "prefix_generation_per_evaluation": 1.0,
    "tables_partial_per_evaluation_cap": 8,
    "note": ("1 次条件评价 = 1 根 × 2 臂 × 2 桌 = 4 桌 tables_full（与 "
             "AV_TABLES_PER_ROOT_EVALUATION 同口径）；上界为声明批 + 阶段 1 + "
             "阶段 2 的合计，实际按被选根计费（不跑整前缀）"),
}


#: 家族根序号上界（A2）：根身份把序号渲染成 root{NNN} 三位字段，越界会让身份
#: 字段宽度漂移（下游按固定宽度解析或人工核对根清单都会失配）；显式选根一律限制在
#: 0..99（与自然面板 MAX_ROOT_INDEX=99 同一纪律）。
AV_FAMILY_ROOT_INDEX_MAX = 99
#: 家族根内容摘要 schema（A2：跑的是哪个根必须可核，不"跑完再丢弃"）。
AV_FAMILY_ROOT_DIGEST_SCHEMA = "sitin-av-family-root-digest/2"
#: 冻结核心根清单（A1）：每（子场景侧 × 对手情景）格的**核心根配额**（§7.3：
#: 每子场景首批 4 个独立来源根、H/M 各 2）。声明与台账都不足以证明"面板已建齐"：
#: 必须逐格按本配额验收。
AV_FAMILY_CORE_ROOTS_PER_CELL = 2

# ===========================================================================
# S4（R9 裁定 §5、权威口径块第 6 条）· 本版**只启用 branch**
#
# 独立复算（裁定原文）：已归档 6 根 / 2,129 帧上，chain / four_white / baotou
# 原有的机会侧 TRUE（3/10/5 帧）在 P9c 新谓词下**全部转 UNKNOWN**——新谓词要求
# **参照分支 c** 的家族支持量已知（Δsupp），而特殊家族无对应路线时投影返回 None。
# 因此"四族无退化"的普遍化结论不成立。把 None 当 0 一律禁止。
#
# 处置：本版只启用 branch；其余三族**显式 inactive**，由调度**明确跳过**并把原因
# 写进状态与产物（不静默、不产生该族任何样本或 epoch）。限定 branch 后可继续有限验收。
# ===========================================================================

#: 本版**启用**的家族集合（写进身份：换集合即换批次身份）。
AV_FAMILY_ENABLED_FAMILIES: Tuple[str, ...] = ("branch",)
#: 本版**显式 inactive** 的家族（调度跳过；不得当成"跑过但无样本"）。
AV_FAMILY_INACTIVE_FAMILIES: Tuple[str, ...] = ("chain", "four_white", "baotou")
#: 逐族具名原因（引用裁定的事实依据；不写成"暂不支持"这种无可核内容的说法）。
AV_FAMILY_INACTIVE_REASONS: Dict[str, str] = {
    "chain": ("S4：独立复算显示 chain 原有机会侧 TRUE（3 帧）在新谓词（Δsupp 需参照"
              "分支的家族支持量已知，特殊家族无对应路线时投影返回 None）下全部转 "
              "UNKNOWN；禁止把 None 当 0。本版不启用，调度跳过"),
    "four_white": ("S4：独立复算显示 four_white 原有机会侧 TRUE（10 帧）在新谓词下全部"
                   "转 UNKNOWN（投影返回 None，禁止把 None 当 0）；本版不启用，调度跳过"),
    "baotou": ("S4：独立复算显示 baotou 原有机会侧 TRUE（5 帧）在新谓词下全部转 "
               "UNKNOWN（投影返回 None，禁止把 None 当 0）；本版不启用，调度跳过"),
}
#: 跳过未启用家族时的具名停因记号（进 state.stop_reason 与批次报告）。
AV_FAMILY_INACTIVE_STOP_REASON = "family_refresh_inactive_family_skipped"


def av_family_scope(channel: Any) -> Dict[str, Any]:
    """家族启用范围判定（S4）：enabled / inactive / unknown 三态 + 具名原因。

    未知族名（不在登记 FAMILIES 里）判 unknown 并拒绝（不猜"它是不是新族"）。
    """

    name = str(channel or "")
    if name in AV_FAMILY_ENABLED_FAMILIES:
        status, reason = "enabled", None
    elif name in AV_FAMILY_INACTIVE_FAMILIES:
        status, reason = "inactive", AV_FAMILY_INACTIVE_REASONS.get(name)
    else:
        status, reason = "unknown", (
            "家族名 {0!r} 不在本版登记范围内（启用 {1}；显式 inactive {2}）："
            "既不接线也不猜测".format(name, list(AV_FAMILY_ENABLED_FAMILIES),
                                      list(AV_FAMILY_INACTIVE_FAMILIES)))
    return {
        "schema": "sitin-av-family-scope/1",
        "channel": name,
        "status": status,
        "reason": reason,
        "enabled_families": list(AV_FAMILY_ENABLED_FAMILIES),
        "inactive_families": list(AV_FAMILY_INACTIVE_FAMILIES),
        "inactive_reasons": dict(AV_FAMILY_INACTIVE_REASONS),
        "stop_reason": None if status == "enabled" else AV_FAMILY_INACTIVE_STOP_REASON,
        "samples_or_epoch_produced": False,
    }


def av_family_scope_allows(channel: Any) -> Tuple[bool, Dict[str, Any]]:
    """(是否允许调度, 范围记录)：inactive/unknown 一律不允许（失败关闭）。"""

    scope = av_family_scope(channel)
    return scope["status"] == "enabled", scope


def av_family_generator_of(prefix_source: Any) -> str:
    """前缀来源 → 生成器版本记号（根身份的一个维度；**单一映射点**）。"""

    opportunities = av_opportunities()
    return (opportunities.GENERATOR_V2_BEHAVIOR
            if str(prefix_source or "") == "v2_behavior"
            else opportunities.GENERATOR_SCRIPTED_FIXTURE)


def av_family_root_descriptor(*, prefix_source: Any, sub_scenario: Any,
                              opponent_mix: Any, panel_seed: Any,
                              root_index: Any) -> Dict[str, Any]:
    """家族根**唯一描述符**（A3）：五个维度 → 身份 + 真实执行种子。

    普通条件生成（sitin_opportunities.generate_opportunity）与指定根入口
    （run_av_evaluation 的单根面板）共用本函数：同一个根在任何入口上都是同一个
    身份、同一个种子，补根因此可以逐字复现同一座牌山。
    身份里**不含候选**：候选属于评价实例（av_instance_identity_key），同根对不同
    候选必须共享同一来源根身份。
    """

    index = av_family_root_index(int(root_index))
    return dict(av_stage().root_descriptor(
        generator=av_family_generator_of(prefix_source),
        sub_scenario=str(sub_scenario), opponent_mix=str(opponent_mix),
        panel_seed=int(panel_seed), root_index=index))


def av_family_root_id(*, prefix_source: Any, sub_scenario: Any, opponent_mix: Any,
                      panel_seed: Any, root_index: Any) -> str:
    """家族根身份（= 描述符的 root_id）：生成器 × 子场景 × 情景 × 种子 × 序号。"""

    return str(av_family_root_descriptor(
        prefix_source=prefix_source, sub_scenario=sub_scenario,
        opponent_mix=opponent_mix, panel_seed=panel_seed,
        root_index=root_index)["root_id"])


def av_family_root_seed(*, prefix_source: Any, sub_scenario: Any, opponent_mix: Any,
                        panel_seed: Any, root_index: Any) -> int:
    """家族根执行种子 = 描述符种子（与普通生成器**同一条式子**，A3）。"""

    return int(av_family_root_descriptor(
        prefix_source=prefix_source, sub_scenario=sub_scenario,
        opponent_mix=opponent_mix, panel_seed=panel_seed,
        root_index=root_index)["root_seed"])


def av_family_legacy_root_id(sub_scenario: Any, root_index: Any) -> str:
    """旧根身份（v1：av-eval-{谓词}:{谓词}:rootNNN）——**仅供识别历史数据**。

    不含对手情景与实际种子，H/M 与跨种子实例同名互吞（复审 A2）；新评价一律不再
    生成这种身份，只用于把历史台账显式判为旧数据（拒绝继承或按原生成器还原种子）。
    """

    return "av-eval-{0}:{0}:root{1:03d}".format(str(sub_scenario), int(root_index))


def av_family_root_identity_fields(root_id: Any) -> Optional[Dict[str, Any]]:
    """v2 根身份 → 五个维度；旧/未知形状返回 None（不猜）。"""

    return av_stage().parse_root_identity(root_id)


def av_family_legacy_identity_fields(root_id: Any) -> Optional[Dict[str, Any]]:
    """旧根身份（v1）→ {root_label, sub_scenario, root_index}；非旧形状返回 None。"""

    return av_stage().parse_legacy_root_identity(root_id)


def av_family_root_seed_of_record(row: Mapping[str, Any]) -> Dict[str, Any]:
    """根记录 → 真实执行种子的**唯一**还原点（A3：不静默赋新种子）。

    三条互斥结论：

      - recovered=True：种子已确定——v2 身份由描述符唯一决定（记录另带实际执行
        种子时逐字核对，不符即拒绝）；旧身份（v1）必须显式声明派生记号 prefix-v1
        且带实际种子，按**原生成器**式子还原并核对。
      - recovered=False 且 problems 非空：缺真实种子或版本不可恢复 → 调用方**停止**
        并说明原因（不调度、不猜、不换种子）。
    """

    stage_mod = av_stage()
    root_id = str(row.get("root_id") or "")
    declared = row.get("root_seed")
    fields = av_family_root_identity_fields(root_id)
    if fields is not None:
        expected = int(stage_mod.root_seed(
            generator=fields["generator"], sub_scenario=fields["sub_scenario"],
            opponent_mix=fields["opponent_mix"], panel_seed=fields["panel_seed"],
            root_index=fields["root_index"]))
        problems: List[str] = []
        for name, actual in (("sub_scenario", str(row.get("sub_scenario") or "")),
                             ("opponent_mix", str(row.get("opponent_mix") or "")),
                             ("panel_seed", row.get("panel_seed")),
                             ("root_index", row.get("root_index"))):
            if actual in (None, ""):
                continue
            if str(actual) != str(fields[name]):
                problems.append(
                    "根身份与记录字段不符：{0} 记录 {1!r} != 身份 {2!r}".format(
                        name, actual, fields[name]))
        if declared is not None and int(declared) != expected:
            problems.append(
                "记录的实际执行种子与根身份派生不符（{0} != {1}）：不采用该结果".format(
                    int(declared), expected))
        if problems:
            return {"root_seed": None, "seed_derivation": None, "recovered": False,
                    "problems": problems, "identity": fields}
        return {"root_seed": expected,
                "seed_derivation": stage_mod.ROOT_SEED_DERIVATION_SHARED,
                "recovered": True, "problems": [], "identity": fields}
    legacy = av_family_legacy_identity_fields(root_id)
    if legacy is None:
        return {"root_seed": None, "seed_derivation": None, "recovered": False,
                "problems": ["根身份无法解析（既不是 v2 完整身份，也不是 v1 历史身份）："
                             "不猜身份、不调度"]}
    derivation = str(row.get("seed_derivation") or "")
    if declared is None:
        return {"root_seed": None, "seed_derivation": derivation or None,
                "recovered": False, "identity": legacy,
                "problems": ["历史根身份（v1）缺实际执行种子：不可恢复"
                             "（不静默赋新种子）"]}
    if derivation != stage_mod.ROOT_SEED_DERIVATION_LEGACY_PREFIX:
        return {"root_seed": None, "seed_derivation": derivation or None,
                "recovered": False, "identity": legacy,
                "problems": ["历史根身份（v1）缺派生版本记号（应为 {0}）：无法确定按"
                             "哪一代生成器还原种子，停止".format(
                                 stage_mod.ROOT_SEED_DERIVATION_LEGACY_PREFIX)]}
    panel_seed = row.get("panel_seed")
    if panel_seed is None:
        return {"root_seed": None, "seed_derivation": derivation,
                "recovered": False, "identity": legacy,
                "problems": ["历史根记录缺面板种子：无法按原生成器还原执行种子"]}
    restored = int(stage_mod.legacy_prefix_root_seed(int(panel_seed), root_id))
    if restored != int(declared):
        return {"root_seed": None, "seed_derivation": derivation,
                "recovered": False, "identity": legacy,
                "problems": ["历史根记录的实际种子与旧生成器派生不符（{0} != {1}）："
                             "不猜种子".format(int(declared), restored)]}
    return {"root_seed": restored, "seed_derivation": derivation,
            "recovered": True, "problems": [], "identity": legacy, "legacy": True}


def _av_family_item_descriptor(item: Mapping[str, Any], *, root_index: Any = None,
                               ) -> Dict[str, Any]:
    """家族评价/补根工作项 → **唯一根描述符**（身份 + 执行种子一次对齐）。

    工作项里的前缀来源（夹具/真实）是身份维度的一部分：同一个根在不同生成器下不是
    同一条证据，因此这里**不设缺省猜测**以外的分支——只把工作项已冻结的参数交给
    描述符，再由调用方核对身份与种子（A3：不等价即拒绝，不启动任何桌赛）。
    """

    if root_index is None:
        indexes = [int(value) for value in (item.get("root_indexes") or ())]
        if len(indexes) != 1:
            raise ValueError("家族工作项必须锁定**恰好一个**根序号，得到 {0}".format(
                indexes))
        root_index = indexes[0]
    return av_family_root_descriptor(
        prefix_source=item.get("prefix_source") or "scripted_fixture",
        sub_scenario=item["sub_scenario"], opponent_mix=item["opponent_mix"],
        panel_seed=item["panel_seed"], root_index=int(root_index))


def av_family_root_index(value: Any) -> int:
    """家族根序号校验（A2）：必须是 0..AV_FAMILY_ROOT_INDEX_MAX 的整数。

    根序号是**根身份字段**（root{NNN}）：越界即身份漂移，一律拒绝（不静默取整、
    不静默截断、不猜调用方意图）。调用方在**一切副作用之前**用它做门。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("家族根序号必须是 int，得到 {0!r}（不做静默取整）".format(value))
    index = int(value)
    if not 0 <= index <= AV_FAMILY_ROOT_INDEX_MAX:
        raise ValueError(
            "家族根序号越界：{0} 不在 0..{1}（根身份渲染成三位字段 rootNNN，越界即"
            "身份漂移：既不是可复现的根，也不该启动任何桌赛）".format(
                index, AV_FAMILY_ROOT_INDEX_MAX))
    return index


def av_family_root_requirement_digest(*, prefix_source: Any, predicate: Any,
                                      opponent_mix: Any, panel_seed: Any,
                                      root_index: Any) -> str:
    """根内容**要求摘要**（执行前即可算）：冻结的复现参数 → 摘要。

    只吃重建参数、不跑任何桌：执行前用它把"本次要跑哪个根"冻结下来，执行后与结果
    声明的摘要逐字比对，因此"跑的是目标任务根"可以被核对，而不是跑完再按身份丢弃。
    A3：摘要里的身份与种子一律取自**唯一根描述符**（生成器 × 子场景 × 情景 × 实际
    种子 × 根索引）——摘要不再是"另一套派生式"的产物。
    """

    descriptor = av_family_root_descriptor(
        prefix_source=prefix_source, sub_scenario=predicate,
        opponent_mix=opponent_mix, panel_seed=panel_seed, root_index=root_index)
    return sha256_text(canonical_json({
        "schema": AV_FAMILY_ROOT_DIGEST_SCHEMA,
        "kind": "requirement",
        "prefix_source": str(prefix_source),
        "predicate": str(predicate),
        "opponent_mix": str(opponent_mix),
        "panel_seed": int(panel_seed),
        "root_index": descriptor["root_index"],
        "root_id": descriptor["root_id"],
        "root_seed": descriptor["root_seed"],
        "generator": descriptor["generator"],
        "root_identity_schema": descriptor["root_identity_schema"],
        "seed_derivation": descriptor["seed_derivation"],
    }))


def av_family_root_content_digest(*, prefix_source: Any, predicate: Any,
                                  opponent_mix: Any, panel_seed: Any,
                                  root_index: Any, snapshot: Mapping[str, Any]) -> str:
    """根内容摘要（执行后从**截取快照**算）：要求摘要 + 实际跑出来的内容指纹。

    要求摘要保证"参数就是冻结的那个根"；内容指纹（截取窗口 / 前缀 / 观察摘要 /
    规格种子）保证"确实跑出了内容"，并让重复执行同一根可以对拍（不重跑、不换牌山）。
    """

    requirement = av_family_root_requirement_digest(
        prefix_source=prefix_source, predicate=predicate, opponent_mix=opponent_mix,
        panel_seed=panel_seed, root_index=root_index)
    return sha256_text(canonical_json({
        "schema": AV_FAMILY_ROOT_DIGEST_SCHEMA,
        "kind": "content",
        "requirement": requirement,
        "content": {
            "source_root_id": snapshot.get("source_root_id"),
            "match_spec_seed": (snapshot.get("match_spec") or {}).get("seed"),
            "cut_window": dict(snapshot.get("cut_window") or {}),
            "legal_action_prefix_sha256": sha256_text(canonical_json(
                list(snapshot.get("legal_action_prefix") or ()))),
            "observation_summary_sha256": sha256_text(canonical_json(
                dict(snapshot.get("observation_summary") or {}))),
        },
    }))


#: 根见证审计附属文件（生产侧落盘名；按实例身份索引，便于长期恢复）。
AV_ROOT_WITNESS_SIDECAR = "root-witnesses.jsonl"
AV_ROOT_WITNESS_DIR = "root-witnesses"
#: 见证记录 schema（见证本体另带 sitin-root-witness/2 序列化版本）。
AV_ROOT_WITNESS_RECORD_SCHEMA = "sitin-root-witness-record/1"


class AvRootWitnessRefused(RuntimeError):
    """见证落盘前的核验未通过（未捕获 / 错绑定 / 观察摘要口径不符）：**拒绝落盘**。

    P16-C3：旧实现在这里只认 capture.source 字符串，等于"自报即收"；现在落盘前
    用完整判定重算（现场捕获物 + 内部根/种子/窗口/观察绑定 + 与面板声明的实例
    身份一致），任一不通过即具名拒绝——不一致的见证不得进审计附属文件。
    """


def av_root_witness_records(out_dir: Path, *, panel: Mapping[str, Any],
                            candidate_id: str, predicate: str, opponent: str,
                            panel_seed: int, prefix_source: str,
                            execution_kind: str, runtime_kind: Optional[str]
                            ) -> List[Dict[str, Any]]:
    """把面板场景里**真实捕获**的根见证落成生产审计附属文件（Q3）。

    - 见证本体来自快照（build_snapshot 的唯一构造点，普通入口与指定根入口同一份
      序列化）；这里只补**可重算**的要求摘要（按冻结计划参数算）并落盘；
    - **只接受带 capture.source=attempt_outcome 的见证**：由计划参数重算出来的东西
      进不了这个文件（它没有现场捕获物）；
    - 落盘两处：追加式 JSONL（本轮全部见证）+ 按实例身份命名的单文件
      （root-witnesses/<根身份摘要>.json，长期恢复时按身份取用，不靠目录名猜）。
    """

    opportunities = av_opportunities()
    records: List[Dict[str, Any]] = []
    for scenario in (panel.get("scenarios") or ()):
        snapshot = scenario.get("snapshot") if isinstance(scenario, Mapping) else None
        witness = (snapshot or {}).get("root_witness")
        if not isinstance(witness, Mapping):
            continue
        capture = witness.get("capture") or {}
        if str(capture.get("source")) != "attempt_outcome":
            # 非现场捕获的东西不进审计文件（不冒充真实见证）。
            continue
        descriptor = dict(witness.get("root_descriptor") or {})
        # —— P16-C3：落盘前**重算并核验**，不只认自报的来源字符串 ——
        # ① 内部绑定：根标识 = 描述符、实际种子 = 描述符种子（真实路由硬缺口）、
        #    窗口座位 = 焦点座位、观察摘要口径与逐字段摘要齐备（给了本体就逐字段重算）；
        # ② 实例身份：描述符的子场景 / 情景 / 面板种子必须与本次面板声明一致；
        # 任一不通过即具名拒绝（不落盘、不冒充真实见证）。
        verdict = opportunities.root_witness_verdict(
            witness,
            observation_summary=(snapshot or {}).get("player_observation_summary"))
        identity_problems = []
        for name, actual, declared in (
                ("sub_scenario", descriptor.get("sub_scenario"), str(predicate)),
                ("opponent_mix", descriptor.get("opponent_mix"), str(opponent)),
                ("panel_seed", descriptor.get("panel_seed"), int(panel_seed))):
            if actual in (None, ""):
                identity_problems.append("根描述符缺 {0}".format(name))
            elif str(actual) != str(declared):
                identity_problems.append(
                    "根描述符的{0}与本面板实例不符（描述符 {1!r} != 面板 {2!r}）".format(
                        name, actual, declared))
        if (verdict["overall_status"] == opportunities.ROOT_WITNESS_OVERALL_REJECTED
                or identity_problems):
            raise AvRootWitnessRefused(
                "根见证落盘前核验未通过（拒绝落盘）：overall_status={0}；"
                "bindings={1}；identity={2}".format(
                    verdict["overall_status"],
                    {key: value for key, value in verdict["binding"].items()
                     if key in ("root_id_matches_source", "seed_matches_descriptor",
                                "window_seat_matches_focal",
                                "observation_summary_checked_against_body",
                                "window_bound_to_observation")},
                    identity_problems or "ok"))
        root_index = descriptor.get("root_index")
        witness = dict(witness)
        if witness.get("requirement_digest") in (None, "") and root_index is not None:
            # **可重算**的那一半在这里补齐（两个入口同一段代码）：由冻结计划参数算出的
            # 要求摘要；它与现场捕获的 content_digest 分开落字段（Q3 裁定）。
            witness["requirement_digest"] = av_family_root_requirement_digest(
                prefix_source=prefix_source, predicate=predicate,
                opponent_mix=opponent, panel_seed=int(panel_seed),
                root_index=int(root_index))
            witness["requirement_source"] = (
                "av_family_root_requirement_digest（由冻结计划参数重算，可与现场内容摘要"
                "分开核对）")
        record = {
            "schema": AV_ROOT_WITNESS_RECORD_SCHEMA,
            "recorded_at_utc": utc_now(),
            "instance": {
                "candidate_id": candidate_id, "predicate": str(predicate),
                "opponent_mix": str(opponent), "panel_seed": int(panel_seed),
                "prefix_source": str(prefix_source), "entry": capture.get("entry"),
                "root_index": root_index, "root_id": descriptor.get("root_id"),
                "root_seed": descriptor.get("root_seed"),
                "execution_kind": str(execution_kind), "runtime_kind": runtime_kind,
                "source_root_id": witness.get("source_root_id"),
            },
            "witness": dict(witness),
        }
        records.append(record)
    if not records:
        return records
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json(record) for record in records]
    with (out_dir / AV_ROOT_WITNESS_SIDECAR).open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")
    for record in records:
        root_id = str((record.get("instance") or {}).get("root_id") or "")
        if not root_id:
            continue
        directory = out_dir / AV_ROOT_WITNESS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        av_atomic_write_json(directory / "{0}.json".format(sha256_text(root_id)[:16]),
                             record)
    return records


def av_conditional_root_selection(value: Any) -> Optional[Tuple[int, ...]]:
    """显式根选择规范化（A2）：None = 不选根（既有"首次命中"行为逐字不变）。

    给出时必须**恰好一个**根序号（一次条件评价 = 1 根 × 2 臂 × 2 桌，与
    AV_TABLES_PER_FAMILY_EVALUATION 同口径）：多个根是多次评价，不能塞进一次
    评价的结果里（否则结果身份与计费都无法对账）。
    """

    if value is None:
        return None
    if isinstance(value, (str, bytes, Mapping)) or isinstance(value, bool):
        raise ValueError("根选择必须是整数序列，得到 {0!r}".format(value))
    try:
        items = [int(item) for item in value]
    except TypeError:
        raise ValueError("根选择必须是整数序列，得到 {0!r}".format(value))
    if len(items) != 1:
        raise ValueError(
            "一次条件评价只能评价一个根（A2：选择集是任务身份的一部分），得到 {0}"
            "个根序号 {1}：多次评价请分次调用".format(len(items), items))
    return (av_family_root_index(items[0]),)


def _av_conditional_driver_config() -> Any:
    """单根条件面板的续打驱动配置（与 sitin_opportunities._driver_config 逐字同口径）。

    必须在**本模块**显式重述（而不是借用对方私有函数）：续打的步数上限决定
    "完整剩余阶段"能不能跑完，两边口径不一致会悄悄改变样本可用性。
    """

    from hangma_bot.application.deadline import BudgetPolicy
    from hangma_bot.offline.evaluate import MatchDriverConfig

    return MatchDriverConfig(clock_mode="logical", step_limit=100000,
                             budget_policy=BudgetPolicy(),
                             competition_tournament_id="sitin-opportunities-c1")


def _av_conditional_root_panel(*, prefix_source: str, predicate_id: str, focal_seat: int,
                               opponent_scenario: str, root_label: str, out_dir: Path,
                               ruleset_version: str, base_score: int,
                               you_cai_bi_kao: bool, attempts_cap: int,
                               panel_seed: int, root_index: int, root_seed: int,
                               authorization_token: Optional[Mapping[str, Any]] = None,
                               runtime: Optional[Mapping[str, Any]] = None,
                               tables_in_stage: int = 2, rounds_per_game: int = 8,
                               contract_file: Optional[Path] = None,
                               candidate_policy: Optional[Any] = None
                               ) -> Mapping[str, Any]:
    """**单根**条件机会面板（A2 修复）：只启动被冻结的那一个根，别的根一张桌都不跑。

    与 build_panel 的分工（如实声明）：契约/规则/对手策略装配、快照、双臂、费用账
    全部复用 sitin_opportunities 的**同一批公开原语**（run_prefix_attempt /
    run_real_prefix_attempt / build_snapshot / run_double_arm / build_cost_record）；
    差别只有一处——前缀执行按**显式根序号**调用一次（build_panel 的
    generate_opportunity 恒从 attempt_index=0 起循环取"首命中根"，无法表达
    "只跑 root005"）。面板 schema 字段与 build_panel 保持同形，消费方无需分支。

    根身份与 generate_opportunity 同源：{root_label}:{predicate}:root{index:03d}；
    真实路由的前缀种子取**已登记的家族根种子**（可复现，不再由循环序号隐式决定）。
    """

    opportunities = av_opportunities()
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig

    index = av_family_root_index(int(root_index))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rule_config = {"ruleset_version": ruleset_version, "base_score": base_score,
                   "you_cai_bi_kao": you_cai_bi_kao}
    rules = HangmaRules(RuleConfig(ruleset_version, base_score, you_cai_bi_kao))
    value_limits = ValueAnalysisLimits()
    contract: Mapping[str, Any] = {}
    if contract_file is not None:
        contract = json.loads(Path(contract_file).read_text(encoding="utf-8"))
    if contract:
        opponent_names = opportunities.opponent_policy_names(contract, opponent_scenario)
        tables_in_stage = int(contract.get("group", {}).get("tables_per_group",
                                                           tables_in_stage))
        rounds_per_game = int(contract.get("versions", {}).get("rounds_per_game",
                                                              rounds_per_game))
    else:
        opponent_names = (["weighted_heuristic_v2"] * 3 if opponent_scenario == "H"
                          else ["weighted_heuristic_v2",
                                "weighted_heuristic_v2_white_guard",
                                "weighted_heuristic_v1"])
    fixture_mode = prefix_source == "scripted_fixture"
    effective_runtime: Optional[Mapping[str, Any]] = None
    prefix_behavior_policies: Optional[Tuple[Any, Any, Any, Any]] = None
    tournament_config: Any = None
    stage_mod = av_stage()
    if not fixture_mode:
        effective_runtime = (
            opportunities.resolve_declared_runtime(runtime,
                                                   where="_av_conditional_root_panel")
            if runtime is not None else opportunities.build_real_runtime(
                rules_config=rules.config, rounds_per_game=int(rounds_per_game),
                seed=stage_mod.derive_seed(panel_seed, "prefix-runtime", root_label),
                scenario_id=root_label))
        prefix_behavior_policies = opportunities.frozen_generation_policies(
            opponent_names=opponent_names, focal_seat=focal_seat,
            monotonic=lambda: 800.0)
        from hangma_bot.kernel.config import TimingConfig, TournamentConfig
        tournament_config = TournamentConfig(
            max_games=1, rounds_per_game=int(rounds_per_game), rules=rules.config,
            timing=TimingConfig(**dict(stage_mod.DEFAULT_TIMING)))
    # A3：单根条件面板的根身份 = **唯一描述符**（与普通生成 generate_opportunity 同源）；
    # root_label 仍用于 match_id/runtime 场景名，但不再充当根身份。
    descriptor = av_family_root_descriptor(
        prefix_source=prefix_source, sub_scenario=predicate_id,
        opponent_mix=opponent_scenario, panel_seed=panel_seed, root_index=index)
    source_root_id = str(descriptor["root_id"])
    match_id = "{0}-{1}-match".format(root_label, prefix_source)
    stage_ledger = {"completed_table_scores": []}
    remaining_schedule = {
        "declared_endpoint": "stage_complete",
        "remaining_tables_after_current": max(0, int(tables_in_stage) - 1),
        "rounds_per_game": int(rounds_per_game),
        "tables_in_stage": int(tables_in_stage),
    }
    # P9 FAMCOST（读数修正）：本路径是**单根面板**——实际尝试数恒为 1，因此
    # cap 必须写真实值 1，不再借用调用方为 tables_partial 预留给出的 attempts_cap
    # （旧读数 total=1 / cap=8 / attempts_exhausted=true 自相矛盾，误导为"还有 7 次"）。
    # 调用方的预留额另存 requested_cap，并给出具名原因。
    counters: Dict[str, Any] = {
        "total": 1, "hit": 0, "missed": 0, "unknown": 0, "errors": 0,
        "cap": 1, "requested_cap": int(attempts_cap),
        "attempts_exhausted": False, "attempts_exhausted_reason": None,
        "single_root_path": True,
        "generator": (opportunities.GENERATOR_V2_BEHAVIOR if prefix_source == "v2_behavior"
                      else opportunities.GENERATOR_SCRIPTED_FIXTURE),
        "attempt_errors": [],
    }
    if prefix_source == "v2_behavior":
        counters["runtime_kind"] = (opportunities.runtime_kind_of(effective_runtime)
                                    if effective_runtime is not None
                                    else opportunities.RUNTIME_KIND_REAL)
        counters["engine_kind"] = opportunities.ENGINE_KIND_BY_RUNTIME_KIND[
            counters["runtime_kind"]]
        counters["execution_kind"] = opportunities.EXECUTION_KIND_BY_RUNTIME_KIND[
            counters["runtime_kind"]]
    else:
        counters["runtime_kind"] = opportunities.RUNTIME_KIND_FIXTURE
        counters["engine_kind"] = opportunities.ENGINE_KIND_BY_RUNTIME_KIND[
            opportunities.RUNTIME_KIND_FIXTURE]
        counters["execution_kind"] = opportunities.EXECUTION_SCRIPTED_FIXTURE
    runtime_evidence: Dict[str, Any] = {
        "runtime_kind": counters["runtime_kind"], "engine_kind": counters["engine_kind"],
        "execution_kind": counters["execution_kind"],
        "runtime_source": ("ScriptedFixtureEngine（夹具路径，零真实桌赛）"
                           if prefix_source != "v2_behavior"
                           else (opportunities.REAL_RUNTIME_SOURCE
                                 if runtime is None
                                 else str(runtime.get("runtime_entry")
                                          or "injected_runtime"))),
        "engine_identity": ({} if prefix_source != "v2_behavior"
                            else dict((effective_runtime or {}).get("engine_identity")
                                      or {})),
        "real_tables": counters["runtime_kind"]
        in opportunities.SELECTION_ELIGIBLE_RUNTIME_KINDS,
    }
    started = time.monotonic()
    attempt: Any = None
    if prefix_source == "v2_behavior":
        try:
            attempt = opportunities.run_real_prefix_attempt(
                runtime=effective_runtime, rules=rules, predicate_id=predicate_id,
                focal_seat=focal_seat, attempt_index=index,
                source_root_id=source_root_id, match_id=match_id,
                tournament_config=tournament_config, seed=int(root_seed),
                value_limits=value_limits,
                behavior_policies_by_seat=prefix_behavior_policies,
                opponent_names=opponent_names,
                opponent_scenario=opponent_scenario)
        except opportunities.RuntimeAssemblyError:
            raise
        except ValueError as error:
            counters["errors"] += 1
            counters["attempt_errors"].append(
                {"attempt_index": index, "source_root_id": source_root_id,
                 "error": str(error)})
    else:
        template_sequence = opportunities.FIXTURE_TEMPLATE_SEQUENCE
        attempt = opportunities.run_prefix_attempt(
            rules=rules, template_id=template_sequence[index % len(template_sequence)],
            predicate_id=predicate_id, focal_seat=focal_seat, attempt_index=index,
            source_root_id=source_root_id, match_id=match_id, value_limits=value_limits)
    scenarios: List[Mapping[str, Any]] = []
    cost_records: List[Mapping[str, Any]] = []
    snapshot: Optional[Mapping[str, Any]] = None
    double_arm: Mapping[str, Any] = {
        "valid": False,
        "arms": {"baseline": {"error": "该根未命中谓词"},
                 "candidate": {"error": "该根未命中谓词"}}}
    if attempt is not None and attempt.status == "hit":
        counters["hit"] = 1
        snapshot = opportunities.build_snapshot(
            prefix_source=prefix_source, attempt=attempt, predicate_id=predicate_id,
            focal_seat=focal_seat, opponent_scenario=opponent_scenario,
            match_id=match_id, stage_ledger=stage_ledger,
            remaining_schedule=remaining_schedule, panel_seed=panel_seed,
            tables_in_stage=int(tables_in_stage), rounds_per_game=int(rounds_per_game),
            runtime_evidence=runtime_evidence,
            # Q3：指定根入口在 build_snapshot 里落**同一份**规范根见证
            # （与普通首命中入口共用序列化；见证只含玩家可见事实）。
            descriptor=descriptor,
            requirement_digest=av_family_root_requirement_digest(
                prefix_source=prefix_source, predicate=predicate_id,
                opponent_mix=opponent_scenario, panel_seed=panel_seed,
                root_index=index),
            witness_entry="conditional_specified_root")
        snapshot["root_selection"] = {
            "selector": "conditional_root", "root_index": index,
            "root_id": source_root_id, "root_seed": int(root_seed),
            "requirement_digest": av_family_root_requirement_digest(
                prefix_source=prefix_source, predicate=predicate_id,
                opponent_mix=opponent_scenario, panel_seed=panel_seed,
                root_index=index),
            "note": ("A2：本次前缀只启动该根（单次调用 run_prefix_attempt / "
                     "run_real_prefix_attempt），不再从 attempt_index=0 循环取首命中根"),
        }
        snapshot["root_content_digest"] = av_family_root_content_digest(
            prefix_source=prefix_source, predicate=predicate_id,
            opponent_mix=opponent_scenario, panel_seed=panel_seed,
            root_index=index, snapshot=snapshot)
        if fixture_mode:
            opponent_policy = opportunities.FixtureBehaviorPolicy(
                "fixture-opponent-standin", prefer=("pass",))
            baseline_focal = opportunities.FixtureBehaviorPolicy(
                "fixture-baseline-focal", prefer=("pass",))
            candidate_focal = opportunities.FixtureBehaviorPolicy(
                "fixture-candidate-focal", prefer=("peng:5w",))
            by_seat_baseline = [None] * 4
            by_seat_candidate = [None] * 4
            for seat in range(4):
                by_seat_baseline[seat] = (baseline_focal if seat == focal_seat
                                          else opponent_policy)
                by_seat_candidate[seat] = (candidate_focal if seat == focal_seat
                                           else opponent_policy)
        else:
            clock = (lambda: 800.0)
            stage_mod = av_stage()
            opponents = [stage_mod.build_panel_policy(name, clock)
                         for name in opponent_names]
            baseline_focal = stage_mod.build_panel_policy(
                opportunities.BASELINE_FOCAL_POLICY, clock)
            if candidate_policy is None:
                # 与 sitin_opportunities._panel_candidate_arm_policy 同一工厂（B3）：
                # 真实路由缺省候选臂焦点策略 = 受限执行器装载的 ActionValuePolicy 种子。
                from hangma_bot.offline.evaluate import build_action_value_offline_policy
                candidate_policy = build_action_value_offline_policy("route_value_seed")
            candidate_focal = candidate_policy
            by_seat_baseline = [None] * 4
            by_seat_candidate = [None] * 4
            opponent_iter_b = iter(opponents)
            opponent_iter_c = iter(opponents)
            for seat in range(4):
                by_seat_baseline[seat] = (baseline_focal if seat == focal_seat
                                          else next(opponent_iter_b))
                by_seat_candidate[seat] = (candidate_focal if seat == focal_seat
                                           else next(opponent_iter_c))
        double_arm = opportunities.run_double_arm(
            rules=rules, snapshot=snapshot,
            baseline_policies_by_seat=by_seat_baseline,
            candidate_policies_by_seat=by_seat_candidate,
            config=_av_conditional_driver_config(), value_limits=value_limits,
            runtime=effective_runtime)
        cost_records.append(opportunities.build_cost_record(
            snapshot=snapshot, double_arm=double_arm, counters=counters,
            opponent_policies=opponent_names, rule_config=rule_config,
            focal_seat=focal_seat))
        scenarios.append({
            "sub_scenario": predicate_id,
            "status": "sampled" if double_arm.get("valid") else "invalid",
            "source_root_id": source_root_id, "snapshot": snapshot,
            "double_arm": double_arm})
    else:
        counters["attempts_exhausted"] = True
        if attempt is not None and attempt.status == "unknown":
            counters["unknown"] = 1
        else:
            counters["missed"] = 1
        # 具名原因：本路径只跑**被冻结的那一座牌山**（指定根），一次尝试后即放弃；
        # 换根/换种子由上层按 §7.2 有界独立根搜索另行声明（P9 FAMCOST）。
        counters["attempts_exhausted_reason"] = (
            "指定根 {0} 未见证谓词（status={1}；真实的执行错误另见 errors 计数）："
            "单根路径只跑被冻结的那一座牌山，不换根顶替".format(
                source_root_id, getattr(attempt, "status", "errors")))
        scenarios.append({
            "sub_scenario": predicate_id, "status": "insufficient",
            "reason": ("指定的根 {0} 未命中谓词（{1}）：A2 只启动目标任务根，不另跑"
                       "其他根来顶替").format(source_root_id,
                                              getattr(attempt, "status", "errors"))})
    runtime_kind = str(counters["runtime_kind"])
    panel = {
        "schema": opportunities.PANEL_SCHEMA,
        "generator": counters["generator"],
        "prefix_source": prefix_source, "fixture_mode": fixture_mode,
        "engine_kind": counters["engine_kind"],
        "execution_kind": counters["execution_kind"],
        "runtime_kind": runtime_kind,
        "engine_identity": (dict((effective_runtime or {}).get("engine_identity") or {})
                            if not fixture_mode else
                            {"class": "ScriptedFixtureEngine", "fixture_mode": True,
                             "engine_version": None}),
        "runtime_assembly": {
            "entry": (str((effective_runtime or {}).get("runtime_entry"))
                      if not fixture_mode else "scripted_fixture_engine"),
            "runtime_kind": runtime_kind, "engine_kind": counters["engine_kind"],
            "explicitly_injected": bool(runtime is not None) if not fixture_mode else False,
            "note": ("单根条件面板（A2）：运行时装配与 build_panel 同一批原语，"
                     "差别只在前缀执行按显式根序号跑一次"),
        },
        "prefix_behavior": (dict(snapshot.get("prefix_behavior") or {})
                            if snapshot is not None else None),
        "selection_eligible": opportunities.selection_eligible_for(runtime_kind),
        "predicate": predicate_id, "focal_seat": focal_seat,
        "opponent_scenario": opponent_scenario, "panel_seed": int(panel_seed),
        "tables_in_stage": int(tables_in_stage),
        "root_selection": {
            "selector": "conditional_root", "indexes": [index],
            "root_ids": [source_root_id], "root_seed": int(root_seed),
            "root_descriptor": dict(descriptor),
            "requirement_digest": av_family_root_requirement_digest(
                prefix_source=prefix_source, predicate=predicate_id,
                opponent_mix=opponent_scenario, panel_seed=panel_seed,
                root_index=index)},
        "prefix_attempt_cap": int(attempts_cap),
        "prefix_attempt_cap_note": (
            "调用方为 tables_partial 预留给出的上限；本面板是**单根路径**，真实尝试"
            "上界恒为 1（见 prefix_attempts.cap / requested_cap，P9 FAMCOST）"),
        "prefix_attempt_errors": list(counters.get("attempt_errors") or []),
        "prefix_attempts": {
            "total": counters.get("total"), "hit": counters.get("hit"),
            "missed": counters.get("missed"), "unknown": counters.get("unknown"),
            "errors": counters.get("errors", 0), "cap": counters.get("cap"),
            "requested_cap": counters.get("requested_cap"),
            "single_root_path": bool(counters.get("single_root_path")),
            "attempts_exhausted": counters.get("attempts_exhausted"),
            "attempts_exhausted_reason": counters.get("attempts_exhausted_reason")},
        "quota_declaration": opportunities.quota_declaration(),
        "scenarios": scenarios, "cost_ledger": cost_records,
        "budget_red_line": {
            "real_table_instances_started": (int(counters.get("total") or 0)
                                             if runtime_kind
                                             in opportunities.SELECTION_ELIGIBLE_RUNTIME_KINDS
                                             else 0),
            "double_table_instances": (int(counters.get("total") or 0)
                                       if runtime_kind
                                       == opportunities.RUNTIME_KIND_TEST_DOUBLE else 0),
            "fixture_table_instances": sum(
                int(record.get("fixture_table_instances") or 0)
                for record in cost_records),
            "execution_kind": counters["execution_kind"],
            "engine_kind": counters["engine_kind"], "runtime_kind": runtime_kind,
            "table_instance_basis": ("单根条件面板：只启动 1 个前缀尝试（被选根）"
                                     "（执行记录 counters.total）"),
            "search_ledger_note": ("单根条件面板（A2）：只跑被冻结的那一个根；"
                                   "运行时种类 {0}").format(runtime_kind),
        },
        "strength_evidence": False,
        "wall_ms_total": round((time.monotonic() - started) * 1000.0, 3),
    }
    write_json(out_dir / "panel.json", panel)
    return panel


def _av_family_root_index_of(root_id: Any) -> Optional[int]:
    """家族根序号（root{NNN} 后缀）；不可解析返回 None（不猜）。"""

    match = re.search(r"root(\d+)$", str(root_id or ""))
    return int(match.group(1)) if match else None


def _av_family_declared_channel(state: Mapping[str, Any]) -> Optional[str]:
    """本迭代**显式声明**的家族通道（未声明即不接线：零家族评价、零行为变化）。"""

    plan = state.get("plan") or {}
    declared = plan.get("family_channel")
    if declared in (None, ""):
        return None
    return av_archive().family_channel_of(declared)


# ===========================================================================
# P9 FAMCOST（2026-09-18）· 家族声明**解析**：声明必须由「可物化」的根构成
#
# 缺陷（run3 实测）：计划声明的代价侧根（branch_cost × H/M × idx1/2）在真实前缀下
# **永不见证**谓词（谓词三个析取项逐项不可达，详见 P9 诊断），而 A1 的不变量要求
# 「声明的每个根都物化齐全才原子提交 epoch」⇒ 家族 epoch 永远建不起来。
#
# 修法（Lead §P2 裁定）：**不动 A1 的不变量**，改"声明从哪来"——开轮在**预算门约束**
# 下做**有界独立根搜索**（§7.2：生成尝试预先分配独立根、首次命中即截取），只把
# **见证到谓词**的根写进该格的**有效声明**；请求逐字保留在计划块里（身份面不变），
# 逐候选根留痕（根身份 × 三值 × 墙余量 × gap × 具名原因），凑不齐即具名停因 + 保原席，
# 绝不放宽逐格配额、绝不放宽预算。
# ===========================================================================

#: P9 FAMCOST：家族声明解析（**换牌山探针**）的成本登记表（代码常数显式表达）。
#:
#: 关口二授权公式当前按"家族根评价 16 次 × 最多 6 轮重试"推（family_fill 类目），实测
#: 恰好覆盖本包新增的探针开销，但公式里没有**显式**为"换牌山探针"留项。本表把口径写进
#: 生产侧，供验收装配代理在重生成计划时按项相加（建议公式见 P9 FIX-REPORT §6e/§9）：
#: 探针 = 1 前缀生成 + 1 部分桌、0 完整桌；每迭代合计 ≤ max_total_probes_per_iteration。
AV_FAMILY_DECLARATION_SEARCH_COST: Dict[str, Any] = {
    "prefix_generation_per_probe": 1.0,
    "tables_partial_per_probe": 1.0,
    "tables_full_per_probe": 0.0,
    "max_candidates_per_cell": 16,
    "max_total_probes_per_iteration": 40,
    "note": ("声明解析在**预算门**下做有界独立根搜索：每个候选根一次前缀探针"
             "（不跑双臂 ⇒ 0 完整桌）；逐格 ≤ max_candidates_per_cell、"
             "每迭代合计 ≤ max_total_probes_per_iteration"),
}

#: 声明解析的**有界**搜索：单格最多试多少个候选根（与预算门共同封顶）。
#: 为什么取这个量级：单位置见证概率按 P9 实测约 1/4（32 根里 11 根出现过墙短局面、
#: 其中 3 根真实命中）。**独立同分布二项假设下**，单格凑齐 2 根配额：
#: 12 个候选 P(X≥2) = 84.1618%（= 1 − 0.75^12 − 12·0.25·0.75^11）、
#: 16 个候选 P(X≥2) = 93.6524%。原文"12 次至少 2 次命中 > 95%"的算术**不成立**
#: （R9 独立验收 §8 指出，本注释按 84.1618% 更正）；而且上述假设是**乐观上界**：
#: 实测命中并非独立同分布（同一根的前缀由冻结身份确定性复现、逐根序号上分布稀疏），
#: 因此真实成功率不因该算式被证明。取 16 只是"把同一个预算花在更靠后的序号上"的
#: 有界截断，不是成功率承诺。**上限之外一律停止并具名留痕**，不做无限重试。
AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES = 16
#: 声明解析的**全局**探针上界（跨格合计）：逐格上界 × 预算门之外再加一道天花板，
#: 免得"一个都不见证"的极端情形把逐格上限在每格各花一遍。
#: 为什么是 16/40：实测代价侧可见证的根在序号上很稀疏（P9 见证图：H {0,2,6,11}、
#: M {4,6,13} 于 0..15 内），刷新批还要跳过**已登记**的根，因此单格要走到 13 号附近
#: 才可能凑齐 2 个新根；40 次前缀 ≈ 最小计划授权（前缀生成 101）的四成，仍留得下
#: 核心根物化与条件评价。
AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES = 40
#: 声明解析未凑齐（预算/候选耗尽）时的具名停因记号。
AV_FAMILY_DECLARATION_UNFILLABLE = "family_declaration_unfillable"
#: 候选根不见证谓词的具名原因（逐条留痕；不静默丢弃、不当成命中）。
AV_FAMILY_ROOT_NOT_WITNESSED = "root_not_witnessed"
#: —— G2（R9 裁定 §4.1）· 刷新声明的**用途**：两种意图必须分开表达 ——
#: 缺陷（run3 实测）：指定旧根 branch_open/H/seed=20260916/root000（实际 seed
#: 66460248753675）被写进 plan.family_refresh，与 root003 一起请求；解析器按
#: 「刷新批不得重复登记」跳过已登记的 root000，实际选了 [3,4]——**指定的旧根被静默
#: 替换**，验收器按固定目录名扫描拿不到它。
#: 修法：声明里显式写 intent：
#:   - reevaluate_registered_root（指定旧根重评）：**逐字使用冻结描述符**（根身份、
#:     子场景、情景、实际 seed、根序号），不经任何替换根搜索；该根会被替换或找不到
#:     （不见证）即**拒绝该验证任务**（fail closed），不得降级成新根发现；
#:   - discover_new_root（新根发现）：保持"排除已登记根"的行为不变。
#: 两者产物按**实例身份**（identity key）索引落盘（purpose_index），不靠固定目录名猜用途。
AV_FAMILY_REFRESH_INTENT_REEVALUATE = "reevaluate_registered_root"
AV_FAMILY_REFRESH_INTENT_DISCOVER = "discover_new_root"
AV_FAMILY_REFRESH_INTENTS: Tuple[str, ...] = (AV_FAMILY_REFRESH_INTENT_REEVALUATE,
                                              AV_FAMILY_REFRESH_INTENT_DISCOVER)
#: 未写 intent 的声明按**新根发现**解释（旧计划逐字不变），但点名的根**已登记**时
#: 拒绝（因为唯一出路是静默替换它——正是 G2 的缺陷）；调用方要重评旧根必须显式声明。
AV_FAMILY_REFRESH_INTENT_DEFAULT = AV_FAMILY_REFRESH_INTENT_DISCOVER
#: 用途记号 → 中文标签（报告与产物里给人看的那一列）。
AV_FAMILY_REFRESH_PURPOSES: Dict[str, str] = {
    AV_FAMILY_REFRESH_INTENT_REEVALUATE: "指定旧根重评",
    AV_FAMILY_REFRESH_INTENT_DISCOVER: "新根发现",
}
#: 指定旧根重评被拒（不见证/预算不足/会被替换）的具名原因前缀。
AV_FAMILY_REEVALUATION_REJECTED = "root_reevaluation_rejected"
#: 声明点了已登记的根却没写用途：拒绝（不静默替换，也不擅自按重评解释）。
AV_FAMILY_INTENT_AMBIGUOUS_REGISTERED = "root_intent_ambiguous_registered_root"
#: 未知用途取值。
AV_FAMILY_INTENT_INVALID = "root_intent_invalid"
#: 用途索引 schema（按实例身份定位来源）。
AV_FAMILY_PURPOSE_INDEX_SCHEMA = "sitin-av-family-declaration-purpose/1"


def av_family_refresh_intent(row: Mapping[str, Any]) -> Optional[str]:
    """声明的用途 → 规范取值；未写取缺省；写了但取值非法返回 None（不猜）。"""

    raw = row.get("intent")
    if raw in (None, ""):
        return AV_FAMILY_REFRESH_INTENT_DEFAULT
    value = str(raw)
    return value if value in AV_FAMILY_REFRESH_INTENTS else None


def av_family_declaration_purpose(intent: Any) -> Optional[str]:
    """用途 → 中文标签（未知返回 None：不猜用途）。"""

    return AV_FAMILY_REFRESH_PURPOSES.get(str(intent))
#: 成本登记表与实际常量**同源核对**（两者漂移即 fail-closed，不让授权公式按旧口径少算）。
if (AV_FAMILY_DECLARATION_SEARCH_COST["max_candidates_per_cell"]
        != AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES
        or AV_FAMILY_DECLARATION_SEARCH_COST["max_total_probes_per_iteration"]
        != AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES):
    raise RuntimeError(
        "AV_FAMILY_DECLARATION_SEARCH_COST 与搜索上界常量不一致：成本登记表必须与"
        "实际搜索上界同源（授权公式据此核算，漂移即少算预算）")
#: 声明解析事务件 schema（逐候选根可核）。
AV_FAMILY_DECLARATION_SCHEMA = "sitin-av-family-declaration/1"


def _av_family_declaration_cells(rows: Sequence[Mapping[str, Any]]) -> Dict[Any, List[Dict[str, Any]]]:
    """声明行 → 逐格（子场景 × 对手情景）视图（保持声明顺序，逐行带原位置）。"""

    cells: Dict[Any, List[Dict[str, Any]]] = {}
    for position, row in enumerate(rows or ()):
        key = (str(row.get("sub_scenario") or ""), str(row.get("opponent_mix") or ""))
        cells.setdefault(key, []).append(dict(row, position=position))
    return cells


def _av_family_witness_assembly(*, plan: Mapping[str, Any], mix: str,
                                root_label: str,
                                test_runtime_factory: Optional[
                                    Callable[[], Mapping[str, Any]]] = None
                                ) -> Dict[str, Any]:
    """见证探针的装配上下文（与单根条件面板**逐项同源**，只少跑双臂）。

    同一合同（group-dev-v1）→ 同一对手情景策略名、同一 tables_in_stage /
    rounds_per_game；同一冻结行为策略工厂（焦点座位=0）；同一 tournament_config
    口径；运行时经 _av_assemble_conditional_runtime 显式装配（fail-closed，
    不回退替身/夹具）。
    """

    opportunities = av_opportunities()
    stage_mod = av_stage()
    contract = json.loads(Path(group_dev_contract_path()).read_text(encoding="utf-8"))
    opponent_names = opportunities.opponent_policy_names(contract, mix)
    tables_in_stage = int(contract.get("group", {}).get("tables_per_group", 2))
    rounds_per_game = int(contract.get("versions", {}).get("rounds_per_game", 8))
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig

    rules = HangmaRules(RuleConfig(AV_CONDITIONAL_RULESET_VERSION, 1, False))
    runtime, assembly = _av_assemble_conditional_runtime(
        plan={"prefix_source": str(plan.get("prefix_source") or "scripted_fixture"),
              "panel_seed": int(plan.get("panel_seed") or 0)},
        test_runtime_factory=test_runtime_factory)
    behavior = opportunities.frozen_generation_policies(
        opponent_names=opponent_names, focal_seat=0, monotonic=lambda: 800.0)
    tournament_config = TournamentConfig(
        max_games=1, rounds_per_game=int(rounds_per_game), rules=rules.config,
        timing=TimingConfig(**dict(stage_mod.DEFAULT_TIMING)))
    return {"rules": rules, "value_limits": ValueAnalysisLimits(), "runtime": runtime,
            "assembly": assembly, "behavior": behavior,
            "opponent_names": opponent_names,
            "tournament_config": tournament_config,
            "tables_in_stage": tables_in_stage, "rounds_per_game": rounds_per_game,
            "root_label": root_label}


def _av_family_witness_readings(frames: Sequence[Mapping[str, Any]],
                                predicate: str) -> Dict[str, Any]:
    """逐帧探针读数 → 一条可判定证据（墙余量下界 / gap 上界 / 严格对计数）。"""

    walls = [f["wall_left"] for f in frames if isinstance(f.get("wall_left"), int)]
    gaps = sorted({int(gap) for frame in frames for gap in (frame.get("gaps") or ())})
    values: Dict[str, int] = {}
    for frame in frames:
        value = str((frame.get("predicate_values") or {}).get(predicate))
        values[value] = values.get(value, 0) + 1
    return {
        "frames": len(frames),
        "wall_left_min": min(walls) if walls else None,
        "wall_left_max": max(walls) if walls else None,
        "gap_min": gaps[0] if gaps else None,
        "gap_max": gaps[-1] if gaps else None,
        "gap_values": gaps,
        "strict_pair_frames": sum(1 for frame in frames
                                  if int(frame.get("strict_pairs") or 0) > 0),
        "predicate_values": values,
        "last_frame": dict(frames[-1]) if frames else None,
    }


def _av_family_declaration_budget_gate(ledger: Optional["ActionValueLedger"]) -> Tuple[bool, Optional[str]]:
    """声明的**预算门**（早于费用）：探针要 1 前缀生成 + 1 部分桌，且补齐后还要能物化。

    返回 (ok, 具名原因)。未授权/未限额的账户返回 ok（不假装知道余量，交由账本在预留时
    拒绝——不静默吞掉账本异常）。
    """

    if ledger is None:
        return True, None
    for account, need in (("prefix_generation", 1.0), ("tables_partial", 1.0)):
        remaining = ledger.remaining(account)
        if remaining is not None and float(remaining) < float(need):
            return False, "budget_insufficient:{0}".format(account)
    roots = _av_refresh_budget(ledger)
    if roots is not None and int(roots) < 1:
        return False, "budget_insufficient:tables_full"
    return True, None


def _av_family_root_witness_probe(*, plan: Mapping[str, Any], ledger: Optional["ActionValueLedger"],
                                  sub_scenario: str, mix: str, panel_seed: int,
                                  root_index: int, assembly: Mapping[str, Any],
                                  iteration_no: Any = None,
                                  probe: Optional[Callable[..., Mapping[str, Any]]] = None
                                  ) -> Dict[str, Any]:
    """一个候选根的**前缀见证探针**（只跑前缀，不跑双臂、不写面板产物）。

    真路径：同一描述符 → 同一根身份与执行种子 → run_real_prefix_attempt（冻结行为
    策略、自然开局、逐帧只读读数经 frame_sink 收集）；账本按"1 前缀生成 + 1 部分桌"
    先预留后结算。测试可经 probe 注入替身（显式测试入口，不参与真实计费）。
    """

    opportunities = av_opportunities()
    descriptor = av_family_root_descriptor(
        prefix_source=str(plan.get("prefix_source") or "scripted_fixture"),
        sub_scenario=sub_scenario, opponent_mix=mix, panel_seed=int(panel_seed),
        root_index=int(root_index))
    record: Dict[str, Any] = {
        "sub_scenario": sub_scenario, "opponent_mix": mix,
        "panel_seed": int(panel_seed), "root_index": int(root_index),
        "root_id": str(descriptor["root_id"]),
        "root_seed": int(descriptor["root_seed"]),
        "generator": str(descriptor["generator"]),
        "root_identity_schema": str(descriptor["root_identity_schema"]),
        "seed_derivation": str(descriptor["seed_derivation"]),
        # P9：step_id 必须带**迭代号**——同一个 (子场景 × 情景 × 根序号) 在不同迭代
        # 上是两次不同的探针任务；缺迭代号时第二次迭代会撞已结算行抛
        # TaskAlreadySettled（本包实测：iter-02 的声明解析被账本拒绝）。
        "step_id": "declare:iter{0}:{1}:{2}-s{3}-idx{4}".format(
            iteration_no if iteration_no is not None else 0, sub_scenario, mix,
            int(panel_seed), int(root_index)),
    }
    if probe is not None:
        verdict = dict(probe(descriptor=descriptor, sub_scenario=sub_scenario,
                             mix=mix, panel_seed=int(panel_seed),
                             root_index=int(root_index),
                             step_id=record["step_id"]))
        witnessed = bool(verdict.pop("witnessed", False))
        record.update(verdict)
        record["witnessed"] = witnessed
        record.setdefault("status", "hit" if witnessed else "miss")
        record.setdefault("reason", "" if witnessed else AV_FAMILY_ROOT_NOT_WITNESSED)
        record.setdefault("readings", {})
        return record
    frames: List[Mapping[str, Any]] = []
    # 恢复先对账（与家族评价同族口径）：同一探针任务重入时，旧账行先处理干净
    # （在途→保守结算；已结算无结果→让位），再预留——不原地重复预留、不重复计费。
    try:
        record["reconcile"] = _av_family_reconcile_attempts(
            ledger, step_prefix=record["step_id"],
            reason="家族声明解析：候选根见证探针（旧尝试让位，费用保留）")
    except AV_LEDGER_FAILURE_ERRORS as error:
        record.update({"status": "errors", "witnessed": False, "readings": {},
                       "reason": "见证探针账本对账失败（{0}）：{1}".format(
                           type(error).__name__, error)})
        return record
    reservation = ledger.reserve(
        step_id=record["step_id"], account="prefix_generation", amount=1.0,
        note="家族声明解析：候选根见证探针（P9 FAMCOST；只跑前缀，不跑双臂）")
    partial = ledger.reserve(
        step_id=record["step_id"] + ":tables-partial", account="tables_partial",
        amount=1.0,
        note="候选根见证探针：被启动的真实桌赛实例（部分桌，上限 1）")
    status = "errors"
    error_text = ""
    try:
        attempt = opportunities.run_real_prefix_attempt(
            runtime=assembly["runtime"], rules=assembly["rules"],
            predicate_id=sub_scenario, focal_seat=0, attempt_index=int(root_index),
            source_root_id=str(descriptor["root_id"]),
            match_id="{0}-{1}-witness".format(sub_scenario, mix),
            tournament_config=assembly["tournament_config"],
            seed=int(descriptor["root_seed"]),
            value_limits=assembly["value_limits"],
            behavior_policies_by_seat=assembly["behavior"],
            opponent_names=assembly["opponent_names"], opponent_scenario=mix,
            config=_av_conditional_driver_config(), frame_sink=frames.append)
        status = str(attempt.status)
    except ValueError as error:
        error_text = "{0}: {1}".format(type(error).__name__, error)
    finally:
        ledger.settle(reservation, actual=1.0,
                      note="候选根见证探针前缀生成 1 次（是否命中见读数）")
        ledger.settle(partial, actual=1.0,
                      note="候选根见证探针启动 1 个真实桌赛实例（部分桌）")
    readings = _av_family_witness_readings(frames, sub_scenario)
    witnessed = status == "hit"
    record.update({
        "status": status, "witnessed": witnessed, "readings": readings,
        "reason": ("" if witnessed else
                   (error_text or ("前缀未见证该谓词（{0}）："
                                   "帧 {1}、墙余量 {2}..{3}、gap {4}..{5}、"
                                   "谓词计数 {6}").format(
                                       AV_FAMILY_ROOT_NOT_WITNESSED,
                                       readings["frames"], readings["wall_left_min"],
                                       readings["wall_left_max"], readings["gap_min"],
                                       readings["gap_max"],
                                       readings["predicate_values"]))),
    })
    return record


def _av_family_registered_root_keys(run_root: Path, channel: str) -> set:
    """本通道**已登记**的根身份键（子场景 × 情景 × 根身份）——刷新批不得重复声明它们。

    登记表缺失/为空时返回空集合（首次建立：没有任何根被占用，全部候选可用）。
    """

    payload = _load_json_file(Path(run_root) / "archive" / "family-roots.json") or {}
    block = (payload.get("channels") or {}).get(channel) or {}
    keys = set()
    for row in (block.get("roots") or ()):
        if not isinstance(row, Mapping):
            continue
        keys.add((str(row.get("sub_scenario") or ""),
                  str(row.get("opponent_mix") or ""),
                  str(row.get("root_id") or "")))
    return keys


def _load_json_file(path: Path) -> Optional[Mapping[str, Any]]:
    """读一个 JSON 产物（缺失/不可解析返回 None，不猜内容）。"""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def av_resolve_family_declarations(state: Dict[str, Any], run_root: Path, *,
                                   ledger: Optional["ActionValueLedger"],
                                   probe: Optional[Callable[..., Mapping[str, Any]]] = None,
                                   test_runtime_factory: Optional[
                                       Callable[[], Mapping[str, Any]]] = None,
                                   ) -> Optional[Dict[str, Any]]:
    """开轮声明的**解析**（P9 FAMCOST）：把请求解析成由**可见证根**构成的有效声明。

    语义（Lead §P2 裁定，不改 A1 不变量）：

    - 请求逐字保留（plan.family_refresh 不动 → 冻结清单身份面与执行器对账不变）；
    - 逐格（子场景 × 情景）在**预算门**下做有界独立根搜索：先试声明给出的根序号
      （身份忠实：声明根能见证就用它），再按序号升序试其余独立根，直到该格凑够
      声明的根数或到达 AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES / 预算门；
    - 每个候选根**逐条留痕**（根身份 × 谓词三值 × 墙余量 × gap × 具名原因），
      不见证的候选绝不写进有效声明、也绝不静默丢弃；
    - 凑不齐即 complete=false + 具名停因（保留原席原 epoch 的路径由补根层走）；
    - 结果写 state["family_refresh_resolved"] 与迭代目录 family-declaration.json。
    """

    channel = _av_family_declared_channel(state)
    if channel is None:
        return None
    allowed, scope = av_family_scope_allows(channel)
    if not allowed:
        # S4：本版未启用的家族**在这里就停**——一个探针都不花，更不换根顶替。
        payload: Dict[str, Any] = {
            "schema": AV_FAMILY_DECLARATION_SCHEMA,
            "channel": channel, "iteration_no": state.get("iteration_no"),
            "run_id": state.get("run_id"),
            "request": [dict(row) for row in ((state.get("plan") or {}).get(
                "family_refresh") or ()) if isinstance(row, Mapping)],
            "resolved": [], "trace": [], "complete": False,
            "stop_reason": AV_FAMILY_INACTIVE_STOP_REASON, "scope": scope,
            "note": ("S4：家族 {0} 在本版显式 inactive（{1}）；调度跳过，不产生该族任何"
                     "样本或 epoch，也不把缺失当 0").format(channel, scope["reason"]),
        }
        state["family_scope"] = scope
        state["family_refresh_resolved"] = payload
        return payload
    plan = state.get("plan") or {}
    request = [dict(row) for row in (plan.get("family_refresh") or ())
               if isinstance(row, Mapping)]
    if not request:
        return None
    # 幂等：同一请求已经解析完（complete=True）就直接复用——重入不再花探针的钱，
    # 也保证同一迭代的声明在重入前后逐字一致（确定性）。
    existing = state.get("family_refresh_resolved") or {}
    if (str(existing.get("channel") or "") == channel
            and list(existing.get("request") or ()) == request
            and existing.get("complete")):
        return existing
    registered = _av_family_registered_root_keys(run_root, channel)
    # —— G2：逐条声明先解析**用途**（未知取值即拒绝该声明，不猜用途）——
    annotated: List[Dict[str, Any]] = []
    intent_problems: List[Dict[str, Any]] = []
    for position, row in enumerate(request):
        intent = av_family_refresh_intent(row)
        if intent is None:
            intent_problems.append({
                "position": position, "declaration": dict(row),
                "intent": row.get("intent"), "code": AV_FAMILY_INTENT_INVALID,
                "reason": ("声明用途取值非法（{0!r}）：只接受 {1}；不猜用途、"
                           "不按缺省解释").format(row.get("intent"),
                                                  list(AV_FAMILY_REFRESH_INTENTS))})
            continue
        annotated.append(dict(row, intent=intent,
                              intent_explicit=row.get("intent") not in (None, "")))
    cells = _av_family_declaration_cells(annotated)
    assemblies: Dict[str, Any] = {}
    trace: List[Dict[str, Any]] = []
    resolved_by_cell: Dict[Any, List[Dict[str, Any]]] = {}
    cell_stop: Dict[Any, Optional[str]] = {}
    rejected_by_cell: Dict[Any, List[Dict[str, Any]]] = {}
    reevaluation_rejections: List[Dict[str, Any]] = []
    budget_stop: Optional[str] = None
    total_stop: Optional[str] = None
    searched = 0

    def _artifact_of(root_id: Any) -> str:
        """按**实例身份**（根身份摘要）定位用途产物：不靠固定目录名猜用途。"""

        return str(Path(str(state.get("iter_dir") or run_root))
                   / "family-declarations"
                   / "{0}.json".format(sha256_text(str(root_id))[:16]))

    def _record_intent(record: Dict[str, Any], intent: str,
                       registered_before: Optional[bool] = None) -> Dict[str, Any]:
        record["intent"] = intent
        record["purpose"] = av_family_declaration_purpose(intent)
        if registered_before is not None:
            record["registered_before"] = bool(registered_before)
        record["artifact"] = _artifact_of(record.get("root_id"))
        return record

    for (sub, mix), rows in sorted(cells.items()):
        if total_stop is not None:
            cell_stop[(sub, mix)] = total_stop
            resolved_by_cell[(sub, mix)] = []
            rejected_by_cell[(sub, mix)] = []
            continue
        panel_seed = int(rows[0].get("panel_seed") or 0)
        cell_key = "{0}|{1}".format(sub, mix)
        reevaluate_rows = [row for row in rows
                           if row.get("intent") == AV_FAMILY_REFRESH_INTENT_REEVALUATE]
        discover_rows = [row for row in rows
                         if row.get("intent") == AV_FAMILY_REFRESH_INTENT_DISCOVER]
        # 本格是否**显式**写了"新根发现"：写了就保持"排除已登记根"的原行为；没写却
        # 点了已登记的根 ⇒ 拒绝（见下）。
        discover_explicit = any(row.get("intent_explicit") for row in discover_rows)
        resolved: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        rejected_by_cell[(sub, mix)] = rejected
        cell_stop[(sub, mix)] = None
        tried = 0

        def _budget_ok() -> bool:
            nonlocal budget_stop
            ok, why = _av_family_declaration_budget_gate(ledger)
            if not ok:
                cell_stop[(sub, mix)] = str(why)
                budget_stop = budget_stop or str(why)
            return ok

        # —— ① 指定旧根重评：逐字使用冻结描述符，**不搜索替换根**；不见证即拒绝 ——
        for row in reevaluate_rows:
            index = int(row.get("root_index") or 0)
            descriptor = av_family_root_descriptor(
                prefix_source=str(plan.get("prefix_source") or "scripted_fixture"),
                sub_scenario=sub, opponent_mix=mix,
                panel_seed=int(row.get("panel_seed") or panel_seed), root_index=index)
            registered_before = (sub, mix, str(descriptor["root_id"])) in registered
            if not _budget_ok():
                rejected.append(_record_intent({
                    "sub_scenario": sub, "opponent_mix": mix, "panel_seed": panel_seed,
                    "root_index": index, "root_id": str(descriptor["root_id"]),
                    "root_seed": int(descriptor["root_seed"]), "cell": cell_key,
                    "requested": True, "witnessed": False, "probed": False,
                    "status": "rejected", "readings": {},
                    "reason": (AV_FAMILY_REEVALUATION_REJECTED +
                               ":budget_insufficient：预算门不足，指定旧根重评**拒绝**"
                               "（不换根顶替、不降级成新根发现）")},
                    AV_FAMILY_REFRESH_INTENT_REEVALUATE, registered_before))
                reevaluation_rejections.append(dict(rejected[-1]))
                cell_stop[(sub, mix)] = (AV_FAMILY_REEVALUATION_REJECTED +
                                         ":budget_insufficient")
                continue
            if mix not in assemblies:
                assemblies[mix] = _av_family_witness_assembly(
                    plan=plan, mix=mix,
                    root_label="av-declare-{0}".format(channel),
                    test_runtime_factory=test_runtime_factory)
            tried += 1
            searched += 1
            record = _av_family_root_witness_probe(
                plan=plan, ledger=ledger, sub_scenario=sub, mix=mix,
                panel_seed=int(row.get("panel_seed") or panel_seed), root_index=index,
                assembly=assemblies[mix],
                iteration_no=state.get("iteration_no"), probe=probe)
            record["requested"] = True
            record["cell"] = cell_key
            trace.append(_record_intent(record, AV_FAMILY_REFRESH_INTENT_REEVALUATE,
                                        registered_before))
            if not record.get("witnessed"):
                # 找不到（该根在此冻结描述符下不见证）⇒ **拒绝该验证任务**：不改写根、
                # 不继续搜索别的根顶替（fail closed，G2）。
                rejection = dict(record, status="rejected", reason=(
                    AV_FAMILY_REEVALUATION_REJECTED + ":" + AV_FAMILY_ROOT_NOT_WITNESSED +
                    "：指定的旧根 {0}（root{1:03d}，实际 seed {2}）在冻结描述符下不见证"
                    "该谓词；按 G2 拒绝该验证任务——不得替换成别的根，也不得降级成"
                    "新根发现").format(descriptor["root_id"], index,
                                       int(descriptor["root_seed"])))
                rejection["purpose"] = av_family_declaration_purpose(
                    AV_FAMILY_REFRESH_INTENT_REEVALUATE)
                rejection["artifact"] = _artifact_of(descriptor["root_id"])
                rejected.append(rejection)
                reevaluation_rejections.append(dict(rejection))
                cell_stop[(sub, mix)] = (AV_FAMILY_REEVALUATION_REJECTED + ":" +
                                         AV_FAMILY_ROOT_NOT_WITNESSED)
                continue
            resolved.append({
                "channel": channel, "sub_scenario": sub, "opponent_mix": mix,
                "panel_seed": int(row.get("panel_seed") or panel_seed),
                "root_index": index,
                "seats_per_root": int(row.get("seats_per_root") or 1),
                "source": "family_declaration_reevaluation",
                "intent": AV_FAMILY_REFRESH_INTENT_REEVALUATE,
                "purpose": av_family_declaration_purpose(
                    AV_FAMILY_REFRESH_INTENT_REEVALUATE),
                "registered_before": bool(registered_before),
                "requested_root_index": index,
                "root_id": record["root_id"], "root_seed": record["root_seed"],
                "generator": record["generator"],
                "root_identity_schema": record["root_identity_schema"],
                "seed_derivation": record["seed_derivation"],
                "artifact": _artifact_of(record["root_id"]),
                "witness": {"status": record["status"],
                            "readings": record["readings"]}})

        # —— ② 新根发现：保持"排除已登记根"的行为不变（含边界与总探针上限） ——
        requested = []
        for row in discover_rows:
            index = row.get("root_index")
            if isinstance(index, int) and index not in requested:
                requested.append(int(index))
        candidates = list(requested) + [
            index for index in range(0, AV_FAMILY_ROOT_INDEX_MAX + 1)
            if index not in requested]
        resolved_discover: List[Dict[str, Any]] = []
        for index in candidates:
            if len(resolved_discover) >= len(discover_rows):
                break
            # 有界：**逐格**候选数上限（不无限重试、不靠预算兜底才发现失控）。
            if tried >= AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES:
                cell_stop[(sub, mix)] = "search_bound_reached"
                break
            if searched >= AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES:
                cell_stop[(sub, mix)] = "search_total_bound_reached"
                total_stop = total_stop or "search_total_bound_reached"
                break
            # 预算门（早于费用）：不足即停，不换根顶替、不伪造命中。
            if not _budget_ok():
                break
            # 刷新批不得重复声明**已登记**的根（重复声明等于"刷新什么都没发生"，
            # 而且会让批内根集与在案根集重合 ⇒ 补根层判 unschedulable/not_promoting）。
            # 建立 epoch 时登记表为空，本规则自然不生效。
            descriptor = av_family_root_descriptor(
                prefix_source=str(plan.get("prefix_source") or "scripted_fixture"),
                sub_scenario=sub, opponent_mix=mix,
                panel_seed=panel_seed, root_index=int(index))
            already = (sub, mix, str(descriptor["root_id"])) in registered
            # 写了 intent=discover_new_root 的声明：保持"排除已登记根"的原行为（跳过）；
            # **没写 intent** 却点了已登记的根：拒绝（唯一出路是静默替换，正是 G2 缺陷）。
            if already and int(index) in requested and not discover_explicit:
                # G2 的原始缺陷点：点了已登记的根、又（缺省）要求"新根发现"——唯一出路
                # 是静默替换它。这里**拒绝该声明**并给出改写指引，不静默换根。
                record = _record_intent({
                    "sub_scenario": sub, "opponent_mix": mix, "panel_seed": panel_seed,
                    "root_index": int(index), "root_id": str(descriptor["root_id"]),
                    "root_seed": int(descriptor["root_seed"]), "cell": cell_key,
                    "requested": True, "witnessed": False, "probed": False,
                    "status": "rejected", "readings": {},
                    "reason": (AV_FAMILY_INTENT_AMBIGUOUS_REGISTERED +
                               "：声明的根 {0} 已在本通道登记，而用途按 {1} 解释——"
                               "继续下去只能把它静默替换成别的根（G2 缺陷）；"
                               "要重评旧根请在声明的 intent 里写 {2}").format(
                                   descriptor["root_id"],
                                   AV_FAMILY_REFRESH_INTENT_DISCOVER,
                                   AV_FAMILY_REFRESH_INTENT_REEVALUATE)},
                    AV_FAMILY_REFRESH_INTENT_DISCOVER, True)
                trace.append(record)
                rejected.append(record)
                cell_stop[(sub, mix)] = AV_FAMILY_INTENT_AMBIGUOUS_REGISTERED
                # fail closed：**清空本格已解析结果并停止搜索**——继续搜下去就是
                # "把点名的旧根静默换成别的根"（G2 缺陷本身）。
                resolved_discover.clear()
                resolved = [row for row in resolved
                            if row.get("intent")
                            != AV_FAMILY_REFRESH_INTENT_DISCOVER]
                break
            if already:
                # 非点名的候选：按原行为跳过（不重复登记、不静默顶替某个点名根）。
                # 建立 epoch 时登记表为空，本规则自然不生效。
                trace.append(_record_intent({
                    "sub_scenario": sub, "opponent_mix": mix, "panel_seed": panel_seed,
                    "root_index": int(index), "root_id": str(descriptor["root_id"]),
                    "root_seed": int(descriptor["root_seed"]), "cell": cell_key,
                    "requested": False, "witnessed": False, "probed": False,
                    "status": "skipped", "readings": {},
                    "reason": ("root_already_registered：该根已在本通道登记"
                               "（刷新批不得重复声明）")},
                    AV_FAMILY_REFRESH_INTENT_DISCOVER, True))
                continue
            if mix not in assemblies:
                assemblies[mix] = _av_family_witness_assembly(
                    plan=plan, mix=mix,
                    root_label="av-declare-{0}".format(channel),
                    test_runtime_factory=test_runtime_factory)
            tried += 1
            searched += 1
            record = _av_family_root_witness_probe(
                plan=plan, ledger=ledger, sub_scenario=sub, mix=mix,
                panel_seed=panel_seed, root_index=int(index),
                assembly=assemblies[mix],
                iteration_no=state.get("iteration_no"), probe=probe)
            record["requested"] = int(index) in requested
            record["cell"] = cell_key
            trace.append(_record_intent(record, AV_FAMILY_REFRESH_INTENT_DISCOVER, False))
            if not record.get("witnessed"):
                continue
            resolved_discover.append({
                "channel": channel, "sub_scenario": sub, "opponent_mix": mix,
                "panel_seed": panel_seed,
                "root_index": int(index), "seats_per_root": int(
                    discover_rows[len(resolved_discover)].get("seats_per_root")
                    or discover_rows[0].get("seats_per_root") or 1),
                "source": "family_declaration_search",
                "intent": AV_FAMILY_REFRESH_INTENT_DISCOVER,
                "purpose": av_family_declaration_purpose(
                    AV_FAMILY_REFRESH_INTENT_DISCOVER),
                "registered_before": False,
                "requested_root_index": int(requested[len(resolved_discover)])
                if len(resolved_discover) < len(requested) else None,
                "root_id": record["root_id"], "root_seed": record["root_seed"],
                "generator": record["generator"],
                "root_identity_schema": record["root_identity_schema"],
                "seed_derivation": record["seed_derivation"],
                "artifact": _artifact_of(record["root_id"]),
                "witness": {"status": record["status"],
                            "readings": record["readings"]}})
        resolved.extend(resolved_discover)
        resolved_by_cell[(sub, mix)] = resolved
        if len(resolved) < len(rows) and not cell_stop[(sub, mix)]:
            cell_stop[(sub, mix)] = AV_FAMILY_DECLARATION_UNFILLABLE
    # —— 顶层停因优先级（G2）——
    # ① 指定旧根重评被拒 / 点了已登记根的用途冲突（**fail closed**：不去换根顶替，
    #    也不降级成新根发现）；② 用途取值非法；③ 预算门（可操作）；④ 凑不齐（结论）。
    short = [key for key in cells if len(resolved_by_cell[key]) < len(cells[key])]
    reason_stop: Optional[str] = None
    for key in sorted(cells):
        reason = str(cell_stop.get(key) or "")
        if (reason.startswith(AV_FAMILY_REEVALUATION_REJECTED)
                or reason == AV_FAMILY_INTENT_AMBIGUOUS_REGISTERED):
            reason_stop = reason
            break
    stop_reason: Optional[str] = None
    if intent_problems:
        stop_reason = AV_FAMILY_INTENT_INVALID
    elif short or any(cell_stop.get(key) for key in cells):
        stop_reason = (reason_stop or budget_stop
                       or AV_FAMILY_DECLARATION_UNFILLABLE)
    resolved_rows = [row for (sub, mix) in cells for row in resolved_by_cell[(sub, mix)]]
    complete = (not intent_problems and not short
                and len(resolved_rows) == len(request) and stop_reason in (None, ""))
    # —— G2：**按实例身份**定位来源的用途索引（不靠固定目录名猜用途）——
    resolved_keys = {(row.get("sub_scenario"), row.get("opponent_mix"),
                      str(row.get("root_id"))) for row in resolved_rows}
    purpose_entries: List[Dict[str, Any]] = []
    for item in trace:
        key = (item.get("sub_scenario"), item.get("opponent_mix"), str(item.get("root_id")))
        purpose_entries.append({
            "schema": AV_FAMILY_PURPOSE_INDEX_SCHEMA,
            "root_id": item.get("root_id"), "root_index": item.get("root_index"),
            "sub_scenario": item.get("sub_scenario"),
            "opponent_mix": item.get("opponent_mix"),
            "panel_seed": item.get("panel_seed"),
            "root_seed": item.get("root_seed"),
            "intent": item.get("intent"), "purpose": item.get("purpose"),
            "requested": bool(item.get("requested")),
            "registered_before": bool(item.get("registered_before")),
            "probed": bool(item.get("probed", True)),
            "witnessed": bool(item.get("witnessed")),
            "status": item.get("status"), "reason": item.get("reason"),
            "resolved": key in resolved_keys, "artifact": item.get("artifact"),
            "cell": item.get("cell")})
    # 逐实例身份落**用途产物**（根身份摘要命名 + 内容里带完整身份与用途）。
    artifacts_written: List[str] = []
    for item in purpose_entries:
        path = item.get("artifact")
        if not path:
            continue
        try:
            av_atomic_write_json(Path(path), {
                "schema": AV_FAMILY_PURPOSE_INDEX_SCHEMA, "channel": channel,
                "iteration_no": state.get("iteration_no"), "run_id": state.get("run_id"),
                "entry": dict(item)})
            artifacts_written.append(str(path))
        except OSError:
            # 附属产物写失败不改结论：索引仍在 family-declaration.json 里（不静默丢结论）。
            continue
    payload: Dict[str, Any] = {
        "schema": AV_FAMILY_DECLARATION_SCHEMA,
        "channel": channel, "iteration_no": state.get("iteration_no"),
        "run_id": state.get("run_id"),
        "request": request,
        "resolved": resolved_rows,
        "trace": trace,
        "complete": bool(complete),
        "stop_reason": (None if complete
                        else (stop_reason or AV_FAMILY_DECLARATION_UNFILLABLE)),
        "purpose_schema": AV_FAMILY_PURPOSE_INDEX_SCHEMA,
        "purpose_index": purpose_entries,
        "purpose_artifacts": artifacts_written,
        "intents": {name: sum(1 for row in annotated if row.get("intent") == name)
                    for name in AV_FAMILY_REFRESH_INTENTS},
        "intent_problems": intent_problems,
        "reevaluation_rejections": reevaluation_rejections,
        "search": {
            "schema": AV_FAMILY_DECLARATION_SCHEMA,
            "max_candidates": AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES,
            "max_total_probes": AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES,
            "candidates_tried": searched,
            "candidates_skipped": sum(1 for row in trace
                                      if not row.get("probed", True)),
            "registered_roots": len(registered),
            "cells": {"{0}|{1}".format(sub, mix): {
                "requested": [row.get("root_index") for row in cells[(sub, mix)]],
                "resolved": [row["root_index"] for row in resolved_by_cell[(sub, mix)]],
                "required": len(cells[(sub, mix)]),
                "witnessed": len(resolved_by_cell[(sub, mix)]),
                "candidates_tried": sum(1 for row in trace
                                        if row.get("cell") == "{0}|{1}".format(sub, mix)
                                        and row.get("probed", True)),
                "candidates_skipped": sum(1 for row in trace
                                          if row.get("cell") == "{0}|{1}".format(sub, mix)
                                          and not row.get("probed", True)),
                "intents": sorted({str(row.get("intent"))
                                   for row in cells[(sub, mix)]}),
                "reevaluate_rejected": [dict(item) for item in
                                        rejected_by_cell.get((sub, mix), ())],
                "stop_reason": cell_stop.get((sub, mix))}
                for (sub, mix) in sorted(cells)},
            "budget": {account: (ledger.remaining(account) if ledger is not None else None)
                       for account in ("prefix_generation", "tables_partial", "tables_full")},
            "note": ("有界独立根搜索（§7.2 生成尝试预分配独立根 × 预算门）：只把见证到"
                     "谓词的根写进该格有效声明；请求逐字保留；逐候选根留痕。"
                     "G2：intent=reevaluate_registered_root（指定旧根重评）逐字使用冻结"
                     "描述符、不见证即**拒绝该验证任务**（不换根顶替）；"
                     "intent=discover_new_root（新根发现）保持排除已登记根的行为不变。"),
        },
        "at_utc": utc_now(),
    }
    state["family_refresh_resolved"] = payload
    iter_dir = Path(str(state.get("iter_dir") or run_root))
    try:
        av_atomic_write_json(iter_dir / "family-declaration.json", payload)
    except OSError as error:
        payload["note"] = "声明解析落盘失败：{0}".format(error)
    return payload


def _av_family_declarations(state: Mapping[str, Any],
                            channel: str) -> Dict[str, Any]:
    """开轮声明的家族刷新批 → 逐条校验的**显式根声明**。

    每条声明必须给全（子场景 × 对手情景 × 面板种子 × 根序号）：家族根身份不含
    种子与情景，未锁定根序号就无法在真实副作用**之前**登记实例（不猜参数）。

    P9 FAMCOST：**优先**用 av_resolve_family_declarations 解析出的有效声明
    （由预算门下的有界独立根搜索得到，每条都见证过谓词）；请求逐字留在
    plan.family_refresh 里供身份核对与审计。没有解析结果（夹具路径、旧状态、
    未接线的调用方）时回退到请求本身 —— 旧行为逐字不变。
    """

    allowed, scope = av_family_scope_allows(channel)
    if not allowed:
        # S4：未启用家族不产生任何声明（调用方据此停为具名跳过，不物化、不建 epoch）。
        return {"declared": [], "problems": [{"channel": channel, "reason": scope["reason"],
                                              "code": AV_FAMILY_INACTIVE_STOP_REASON}],
                "declaration_source": "inactive_family",
                "declaration_complete": False, "scope": scope}
    plan = state.get("plan") or {}
    resolved = state.get("family_refresh_resolved") or {}
    source_rows: Sequence[Mapping[str, Any]] = list(plan.get("family_refresh") or ())
    declaration_source = "plan.family_refresh"
    if (str(resolved.get("channel") or "") == channel
            and list(resolved.get("resolved") or ())):
        source_rows = list(resolved["resolved"])
        declaration_source = "family_refresh_resolved"
    allowed = {"{0}_open".format(channel), "{0}_cost".format(channel)}
    declared: List[Dict[str, Any]] = []
    declared_by_root: Dict[str, Dict[str, Any]] = {}
    problems: List[Dict[str, Any]] = []
    for entry in source_rows:
        if not isinstance(entry, Mapping):
            problems.append({"declaration": entry, "reason": "声明不是映射"})
            continue
        if str(entry.get("channel") or channel) != channel:
            continue
        sub = str(entry.get("sub_scenario") or "")
        mix = str(entry.get("opponent_mix") or "")
        seed = entry.get("panel_seed")
        raw_index = entry.get("root_index")
        index = (int(raw_index) if isinstance(raw_index, int)
                 or (isinstance(raw_index, str) and raw_index.lstrip("-").isdigit())
                 else None)
        row = {"channel": channel, "sub_scenario": sub, "opponent_mix": mix,
               "panel_seed": seed, "root_index": index,
               "seats_per_root": int(entry.get("seats_per_root") or 1),
               "source": str(entry.get("source") or declaration_source),
               # G2：用途随声明一起传递（产物按实例身份索引，不靠目录名猜用途）。
               "intent": (str(entry.get("intent"))
                          if entry.get("intent") in AV_FAMILY_REFRESH_INTENTS
                          else AV_FAMILY_REFRESH_INTENT_DISCOVER),
               "purpose": entry.get("purpose") or av_family_declaration_purpose(
                   entry.get("intent")),
               "registered_before": entry.get("registered_before"),
               "artifact": entry.get("artifact")}
        if sub not in allowed:
            problems.append(dict(row, reason="子场景必须属于本族 {0}".format(sorted(allowed))))
            continue
        if mix not in av_archive().OPPONENT_MIXES:
            problems.append(dict(row, reason="对手情景必须是 H/M"))
            continue
        if not isinstance(seed, int):
            problems.append(dict(row, reason="声明缺面板种子：不猜复现参数"))
            continue
        if index is None:
            problems.append(dict(row, reason=(
                "声明缺 root_index：家族根身份不含面板种子，未锁定根序号就无法在"
                "评价前登记实例（不猜）")))
            continue
        if row["seats_per_root"] <= 0:
            problems.append(dict(row, reason="座位数必须为正"))
            continue
        try:
            # A2：根序号是根身份字段（rootNNN），越界即身份漂移——在**解析期**就拦下，
            # 不进入补根调度（不启动任何桌赛）。
            index = av_family_root_index(index)
        except ValueError as error:
            problems.append(dict(row, reason=str(error)))
            continue
        row["root_index"] = index
        # A3：根身份与执行种子都取自**唯一描述符**（生成器 × 子场景 × 情景 × 实际
        # 种子 × 根序号）——声明冻结的就是"要跑的那座牌山"，与普通生成同源。
        descriptor = av_family_root_descriptor(
            prefix_source=plan.get("prefix_source") or "scripted_fixture",
            sub_scenario=sub, opponent_mix=mix, panel_seed=seed, root_index=index)
        row["root_seed"] = int(descriptor["root_seed"])
        row["root_id"] = str(descriptor["root_id"])
        row["generator"] = str(descriptor["generator"])
        row["root_identity_schema"] = str(descriptor["root_identity_schema"])
        row["seed_derivation"] = str(descriptor["seed_derivation"])
        prior = declared_by_root.get(row["root_id"])
        if prior is not None:
            # 同一声明重复：参数逐字一致 → 去重（不是两个根）；不一致 → 冲突，
            # 交由调用方先处理（A1：冲突声明不得被"宣布建立完成"掩盖）。
            fields = ("sub_scenario", "opponent_mix", "panel_seed", "root_index",
                      "root_seed", "seats_per_root")
            if [prior.get(name) for name in fields] != [row.get(name) for name in fields]:
                problems.append(dict(row, reason=(
                    "同一声明重复且参数不一致（{0} != {1}）：冲突声明，不进入建立"
                    "验收").format([prior.get(name) for name in fields],
                                   [row.get(name) for name in fields])))
            continue
        declared_by_root[row["root_id"]] = row
        declared.append(row)
    return {"declared": declared, "problems": problems,
            "declaration_source": declaration_source,
            "declaration_complete": bool(resolved.get("complete"))
            if declaration_source == "family_refresh_resolved" else None}


def _av_family_root_row(*, channel: str, sub_scenario: Any, opponent_mix: Any,
                        root_id: Any, panel_seed: Any, root_index: Any,
                        root_seed: Any, seats_per_root: Any, source: str,
                        prefix_source: Any,
                        descriptor: Optional[Mapping[str, Any]] = None,
                        ) -> Dict[str, Any]:
    """家族根台账行（**唯一**构造点）：身份 × 种子 × 复现参数一次对齐。

    A3：登记方不再另算派生式——有描述符（普通生成的快照/补根产物都带）就用描述符，
    没有就从 v2 身份解析重建；种子统一由 av_family_root_seed_of_record 还原：v2 身份
    唯一确定、v1 历史身份必须按**原生成器**还原，缺真实种子/版本即记 problems（上层
    停止并说明原因，不静默赋新种子）。
    """

    # 身份字段的**缺省来源**是根身份本身（v2 身份自带五维）；调用方显式给出的值
    # 一律当作"声明值"参与一致性核对（不一致 = 身份冲突，不静默覆盖）。
    identity_fields = av_family_root_identity_fields(root_id) or {}
    if root_index is None and identity_fields.get("root_index") is not None:
        root_index = identity_fields["root_index"]
    if panel_seed is None and identity_fields.get("panel_seed") is not None:
        panel_seed = identity_fields["panel_seed"]
    if not sub_scenario and identity_fields.get("sub_scenario"):
        sub_scenario = identity_fields["sub_scenario"]
    if not opponent_mix and identity_fields.get("opponent_mix"):
        opponent_mix = identity_fields["opponent_mix"]
    row: Dict[str, Any] = {
        "channel": channel, "sub_scenario": str(sub_scenario or ""),
        "opponent_mix": str(opponent_mix or ""), "root_id": str(root_id or ""),
        "root_index": (int(root_index) if root_index is not None else None),
        "panel_seed": panel_seed, "root_seed": root_seed,
        "seats_per_root": int(seats_per_root or 1), "source": source,
        "prefix_source": str(prefix_source or "scripted_fixture")}
    mismatches: List[str] = []
    if isinstance(descriptor, Mapping) and descriptor.get("root_id"):
        # 身份与行字段必须一致：不一致即**记问题**（不静默按描述符覆盖）——
        # "同一根两种复现参数"是身份冲突，必须显式暴露给上层拒绝。
        for name, declared in (("sub_scenario", row["sub_scenario"]),
                               ("opponent_mix", row["opponent_mix"]),
                               ("panel_seed", row["panel_seed"]),
                               ("root_index", row["root_index"])):
            if declared in (None, ""):
                continue
            if str(declared) != str(descriptor.get(name)):
                mismatches.append(
                    "记录字段与根描述符不符：{0} {1!r} != {2!r}".format(
                        name, declared, descriptor.get(name)))
        if (descriptor.get("root_seed") is not None
                and row.get("root_seed") is not None
                and int(row["root_seed"]) != int(descriptor["root_seed"])):
            mismatches.append(
                "记录的真实执行种子与根描述符不符（{0} != {1}）".format(
                    int(row["root_seed"]), int(descriptor["root_seed"])))
        row.update({"root_id": str(descriptor["root_id"]),
                    "sub_scenario": str(descriptor.get("sub_scenario")
                                          or row["sub_scenario"]),
                    "opponent_mix": str(descriptor.get("opponent_mix")
                                         or row["opponent_mix"]),
                    "panel_seed": descriptor.get("panel_seed", panel_seed),
                    "root_index": descriptor.get("root_index", root_index),
                    "generator": str(descriptor.get("generator") or ""),
                    "root_identity_schema": str(
                        descriptor.get("root_identity_schema") or ""),
                    "seed_derivation": str(descriptor.get("seed_derivation") or "")})
        if descriptor.get("root_seed") is not None:
            row["root_seed"] = int(descriptor["root_seed"])
    verdict = av_family_root_seed_of_record(row)
    row["root_seed"] = verdict.get("root_seed")
    row["seed_derivation"] = (verdict.get("seed_derivation")
                              if verdict.get("seed_derivation") is not None
                              else row.get("seed_derivation"))
    row["legacy"] = bool(verdict.get("legacy"))
    row["problems"] = mismatches + list(verdict.get("problems") or ())
    identity = verdict.get("identity") or {}
    row.setdefault("generator", str(identity.get("generator") or ""))
    return row


def _av_family_root_records(state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """本迭代**可选留**家族证据产出的根记录（根事实 + 复现参数）。

    只登记可选留（真实运行时）证据产出的根：夹具/替身样本不得进开发根台账
    （A1 同一条纪律）；补根/声明评价的产出由 family_fill.productions 带入。
    A3：身份与真实执行种子取自样本/产出携带的**根描述符**（普通生成快照里就有），
    登记方不再另立派生式；缺描述符时按 v2 身份解析重建，历史（v1）身份显式标注
    legacy 并记 problems，交给上层拒绝或按原生成器还原。
    """

    plan = state.get("plan") or {}
    prefix_source = plan.get("prefix_source") or "scripted_fixture"
    rows: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    evaluation = state.get("conditional_result") or {}
    selectable, _excluded = _av_split_selectable(evaluation.get("samples") or [])
    for sample in selectable:
        sub = str(sample.get("scenario") or "")
        channel = av_archive().family_channel_of(sub)
        if channel is None:
            continue
        root_id = str(sample.get("source_root_id") or "")
        mix = str(sample.get("opponent_mix") or "")
        index = sample.get("root_index")
        if index is None:
            index = _av_family_root_index_of(root_id)
        descriptor = sample.get("root_descriptor")
        if isinstance(descriptor, Mapping) and descriptor.get("root_id"):
            row = _av_family_root_row(
                channel=channel, sub_scenario=sub, opponent_mix=mix, root_id=root_id,
                panel_seed=sample.get("panel_seed"), root_index=index,
                root_seed=sample.get("root_seed"), seats_per_root=1,
                source="conditional_evaluation", prefix_source=prefix_source,
                descriptor=descriptor)
        else:
            # 结果未带描述符（历史产物/他来源样本）：从身份重建——v2 身份自带五个
            # 维度；v1 身份只留 legacy 标注与问题清单（不猜种子）。
            fields = av_family_root_identity_fields(root_id)
            row = _av_family_root_row(
                channel=channel, sub_scenario=sub, opponent_mix=mix, root_id=root_id,
                panel_seed=sample.get("panel_seed"),
                root_index=index, root_seed=sample.get("root_seed"),
                seats_per_root=1, source="conditional_evaluation",
                prefix_source=prefix_source)
        rows[(channel, sub, row["opponent_mix"], row["root_id"])] = row
    for row in (state.get("family_fill") or {}).get("productions") or []:
        if not isinstance(row, Mapping):
            continue
        sub = str(row.get("sub_scenario") or "")
        channel = av_archive().family_channel_of(sub)
        if channel is None:
            continue
        root_id = str(row.get("root_id") or "")
        index = row.get("root_index")
        if index is None:
            index = _av_family_root_index_of(root_id)
        built = _av_family_root_row(
            channel=channel, sub_scenario=sub,
            opponent_mix=str(row.get("opponent_mix") or ""), root_id=root_id,
            panel_seed=row.get("panel_seed"), root_index=index,
            root_seed=row.get("root_seed"),
            seats_per_root=int(row.get("seats_per_root") or 1),
            source="family_fill", prefix_source=prefix_source,
            descriptor=row.get("root_descriptor"))
        rows[(channel, sub, built["opponent_mix"], built["root_id"])] = built
    return [rows[key] for key in sorted(rows)]


def _av_record_family_roots(run_root: Path,
                            state: Mapping[str, Any]) -> Dict[str, Any]:
    """家族根台账（archive/family-roots.json）：按通道累积，跨运行链继承。

    与 normal-roots.json 同构（同一个"根台账随运行链传递、换 --out 不重置"纪律）；
    同格不同复现参数 → 记 conflicts 并保留先到者（不静默取其一）。
    """

    run_root = Path(run_root)
    archive_mod = av_archive()
    channels: Dict[str, Dict[str, Dict[str, Any]]] = {}
    conflicts: List[Dict[str, Any]] = []

    def _merge(row: Mapping[str, Any]) -> None:
        channel = str(row.get("channel") or "")
        if channel not in archive_mod.FAMILIES:
            return
        bucket = channels.setdefault(channel, {})
        cell = "{0}|{1}|{2}".format(row.get("sub_scenario"), row.get("opponent_mix"),
                                    row.get("root_id"))
        prior = bucket.get(cell)
        if prior is None:
            bucket[cell] = dict(row)
            return
        fields = ("root_index", "panel_seed", "root_seed", "seats_per_root")
        if [prior.get(name) for name in fields] != [row.get(name) for name in fields]:
            conflicts.append({"cell": cell, "kept": dict(prior), "seen": dict(row),
                              "note": "同格不同复现参数：保留先到者并登记（不猜）"})

    for directory in _av_chain_archive_dirs(state, run_root):
        path = Path(directory) / "family-roots.json"
        if not path.is_file():
            continue
        try:
            frozen = _av_frozen_input_bytes(state, path)
            payload = json.loads(frozen.decode("utf-8") if frozen is not None
                                 else path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for channel, block in (payload.get("channels") or {}).items():
            for row in ((block or {}).get("roots") or ()):
                if isinstance(row, Mapping):
                    _merge(dict(row, channel=str(row.get("channel") or channel)))
    for row in _av_family_root_records(state):
        _merge(row)
    payload = {"schema": AV_FAMILY_ROOTS_SCHEMA,
               "channels": {channel: {"roots": [bucket[key] for key in sorted(bucket)]}
                            for channel, bucket in sorted(channels.items())}}
    av_atomic_write_json(run_root / "archive" / "family-roots.json", payload)
    return {"channels": payload["channels"], "conflicts": conflicts}


def _av_family_root_registry(channels: Mapping[str, Any]) -> Dict[str, Any]:
    """家族根**复现登记表**：完整根身份 → 复现参数；缺登记/身份冲突即不可调度。

    A2/A3：格键 =（子场景 | 对手情景 | **完整根身份**）——身份自带生成器/情景/实际
    种子/根索引，H 与 M、同索引跨种子都是不同的根（旧实现的裸根名去重会把它们压成
    一条）。行里的字段与身份不符即记 conflicts 并**不启用**该根；历史（v1）身份、
    缺真实执行种子的行一律进 refused（显式停止，不静默赋新种子）。
    """

    cells: Dict[str, Dict[str, Any]] = {}
    combos: Dict[str, List[str]] = {}
    conflicts: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    roots: List[str] = []
    by_cell: Dict[str, List[str]] = {}
    for channel, block in sorted((channels or {}).items()):
        for row in ((block or {}).get("roots") or ()):
            if not isinstance(row, Mapping):
                continue
            sub = str(row.get("sub_scenario") or "")
            mix = str(row.get("opponent_mix") or "")
            root_id = str(row.get("root_id") or "")
            index = row.get("root_index")
            if index is None:
                index = _av_family_root_index_of(root_id)
            # 种子还原走**唯一**入口：v2 身份唯一确定、v1 历史身份按原生成器还原，
            # 缺真实种子/版本即 problems（不静默赋新种子）。
            verdict = av_family_root_seed_of_record(dict(row))
            cell_key = "{0}|{1}|{2}".format(sub, mix, root_id)
            problems = (list(verdict.get("problems") or ())
                        + list(row.get("problems") or ()))
            if problems or verdict.get("root_seed") is None:
                refused.append({"cell": cell_key, "channel": channel,
                                "root_id": root_id, "legacy": bool(verdict.get("legacy")),
                                "problems": problems or ["根种子无法还原"],
                                "note": ("历史/不可恢复的根：不调度、不静默赋新种子"
                                         "（按原生成器还原或重开新身份目录）")})
                continue
            record = {"channel": channel, "sub_scenario": sub, "opponent_mix": mix,
                      "root_id": root_id,
                      "root_index": (int(index) if index is not None else None),
                      "root_seed": int(verdict["root_seed"]),
                      "seed_derivation": verdict.get("seed_derivation"),
                      "generator": (verdict.get("identity") or {}).get("generator"),
                      "panel_seed": row.get("panel_seed"),
                      "seats_per_root": int(row.get("seats_per_root") or 1)}
            prior = cells.get(cell_key)
            if prior is not None and prior != record:
                conflicts.append({"cell": cell_key, "kept": prior, "seen": record,
                                  "note": ("同一根身份出现不同复现参数：不启用该根"
                                           "（不猜）")})
                cells.pop(cell_key, None)
                continue
            cells[cell_key] = record
            if record["panel_seed"] is not None and record["root_index"] is not None:
                combo = "{0}|{1}|{2}".format(sub, mix, record["panel_seed"])
                bucket = combos.setdefault(combo, [])
                if root_id not in bucket:
                    bucket.append(root_id)
            if root_id not in roots:
                roots.append(root_id)
            bucket_cell = by_cell.setdefault("{0}|{1}".format(sub, mix), [])
            if root_id not in bucket_cell:
                bucket_cell.append(root_id)
    return {"cells": cells,
            "roots": sorted(roots),
            "cells_by_side_mix": {key: sorted(value)
                                  for key, value in sorted(by_cell.items())},
            "combos": {key: sorted(value) for key, value in combos.items()},
            "conflicts": conflicts,
            "refused": refused,
            "ambiguous_combos": sorted(key for key, value in combos.items()
                                       if len(value) > 1),
            "n_roots": len(cells)}


def _av_family_epoch_identity_problems(channels: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """家族 epoch 根的**身份核验**（A2/A3）：每个根必须是 v2 完整身份且与行字段一致。

    旧身份（v1，不含情景与实际种子）与当前身份不可比：同一根在旧 epoch 上"是哪个
    牌山"无从确定，继续继承会把两个不同的根当成同一个去做同根比较 → 显式拒绝。
    """

    problems: List[Dict[str, Any]] = []
    for channel, epoch in sorted((channels or {}).items()):
        for row in ((epoch or {}).get("roots") or ()):
            if not isinstance(row, Mapping):
                problems.append({"channel": channel, "reason": "epoch 根行不是映射"})
                continue
            root_id = str(row.get("root_id") or "")
            fields = av_family_root_identity_fields(root_id)
            if fields is None:
                problems.append({"channel": channel, "root_id": root_id, "reason": (
                    "epoch 根身份不是 v2 完整身份（旧格式或未知）：继承会让不同牌山"
                    "同名比较，拒绝")})
                continue
            for name in ("sub_scenario", "opponent_mix"):
                declared = row.get(name)
                if declared in (None, ""):
                    continue
                if str(declared) != str(fields[name]):
                    problems.append({"channel": channel, "root_id": root_id, "reason": (
                        "epoch 根行字段与身份不符：{0} {1!r} != {2!r}".format(
                            name, declared, fields[name]))})
    return problems


def _av_family_inherited_epochs(state: Mapping[str, Any], run_root: Path
                                ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """同一运行链上的家族 epoch 表（每通道一份；没有即空表 + 来源记录）。

    R9/A2：旧 schema（/1）与旧根身份的 epoch **显式拒绝继承**——prov 里带
    identity_problems，调用方据此保持 pending 并说明原因，不静默按新身份续写。
    """

    run_root = Path(run_root)
    recorded = ((state.get("plan") or {}).get("archive_in") or {}).get("path")
    for directory in _av_chain_archive_dirs(state, run_root):
        path = Path(directory) / "family-epochs.json"
        if not path.is_file():
            continue
        try:
            frozen = _av_frozen_input_bytes(state, path)
            payload = json.loads(frozen.decode("utf-8") if frozen is not None
                                 else path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if Path(directory) == run_root / "archive":
            source = "local"
        elif recorded and Path(directory) == Path(recorded).parent:
            source = "archive_in"
        else:
            source = "chain"
        schema = str(payload.get("schema"))
        prov = {"source": source, "path": str(path), "dir": str(directory),
                "schema": schema, "identity_problems": []}
        if schema != AV_FAMILY_EPOCHS_SCHEMA:
            if schema == AV_FAMILY_EPOCHS_SCHEMA_LEGACY:
                prov["identity_problems"] = [{
                    "channel": None, "path": str(path), "reason": (
                        "家族 epoch 表是旧 schema {0}：旧根身份与新身份不可比，"
                        "拒绝继承（旧目录不得续跑，请以新身份在新目录重开）").format(
                            AV_FAMILY_EPOCHS_SCHEMA_LEGACY)}]
                return ({}, prov)
            continue
        channels = dict(payload.get("channels") or {})
        problems = _av_family_epoch_identity_problems(channels)
        if problems:
            prov["identity_problems"] = problems
            return ({}, prov)
        return (channels, prov)
    return ({}, {"source": "none", "path": None, "dir": None,
                 "identity_problems": []})


def _av_write_family_epochs(path: Path, channels: Mapping[str, Any]) -> None:
    """家族 epoch 表原子落盘（每通道一份，与 normal-epoch.json 同构）。"""

    av_atomic_write_json(Path(path), {
        "schema": AV_FAMILY_EPOCHS_SCHEMA,
        "channels": {channel: dict(epoch)
                     for channel, epoch in sorted((channels or {}).items())}})


def _av_family_root_identity_key(row: Mapping[str, Any]) -> str:
    """家族根**完整身份键**（A2）：去重与相等只认完整身份，不认裸根名。

    旧实现按不含对手情景与实际种子的裸 root_id 去重：同索引的 H/M 是同一个键（8 个
    评价项只剩 4 个 H），换 panel_seed 保留序号时新根全被旧 epoch 过滤（刷新批变 0）。
    候选身份**不进**此键：同根对不同候选必须共享同一来源根身份（评价实例另计）。
    """

    root_id = str(row.get("root_id") or "")
    if av_family_root_identity_fields(root_id) is not None:
        return root_id
    # 旧/未知身份：加显式前缀，**不可能**与 v2 身份相等（不静默当成同一个根）。
    return "legacy-root:{0}".format(root_id)


def _av_family_core_matrix(channel: str,
                           registry: Mapping[str, Any]) -> Dict[str, Any]:
    """冻结核心根清单的**逐格验收**（A1）：每（子场景侧 × 对手情景）格的核心根配额。

    声明齐、两侧齐、H/M 齐都不能证明"面板已建齐"：必须逐格数**已登记的核心根**
    （§7.3 每格 {0} 根）。缺格即输入不足，调用方保持 pending，不得宣布建立完成。
    """.format(AV_FAMILY_CORE_ROOTS_PER_CELL)

    by_cell = registry.get("cells_by_side_mix") or {}
    cells: Dict[str, Dict[str, Any]] = {}
    missing: List[Dict[str, Any]] = []
    for side in AV_FAMILY_SIDES:
        sub = "{0}_{1}".format(channel, side)
        for mix in av_archive().OPPONENT_MIXES:
            key = "{0}|{1}".format(sub, mix)
            roots = list(by_cell.get(key) or ())
            ok = len(roots) >= AV_FAMILY_CORE_ROOTS_PER_CELL
            cells[key] = {"sub_scenario": sub, "opponent_mix": mix,
                          "roots": roots, "n_roots": len(roots),
                          "required": AV_FAMILY_CORE_ROOTS_PER_CELL, "ok": ok}
            if not ok:
                missing.append(dict(cells[key], reason=(
                    "核心格缺根：{0} × {1} 已登记 {2}/{3} 根".format(
                        sub, mix, len(roots), AV_FAMILY_CORE_ROOTS_PER_CELL))))
    return {"channel": channel, "cells": cells, "missing": missing,
            "complete": not missing,
            "n_roots": sum(len(cell["roots"]) for cell in cells.values()),
            "required_per_cell": AV_FAMILY_CORE_ROOTS_PER_CELL}


def _av_family_core_evidence_gaps(entry: Optional[Mapping[str, Any]],
                                  core_roots: Sequence[Mapping[str, Any]],
                                  ) -> List[Dict[str, Any]]:
    """入席候选对**全部核心根**的合格评价缺口（A1）：逐根查情景限定证据格。

    "两侧集合齐全"不等于"候选对每个核心根都有合格评价"：缺任一根即不得提交席位
    （建立成功但席位为空 / 席位只覆盖部分核心根都是同一类假完成）。
    """

    archive_mod = av_archive()
    rows = (entry or {}).get("family_evaluations") or {}
    gaps: List[Dict[str, Any]] = []
    for root in core_roots:
        sub = str(root.get("sub_scenario") or "")
        mix = str(root.get("opponent_mix") or "")
        root_id = str(root.get("root_id") or "")
        record = archive_mod.family_cell_lookup(rows.get(sub) or {}, mix, root_id)
        if record is None:
            gaps.append({"sub_scenario": sub, "opponent_mix": mix, "root_id": root_id,
                         "reason": "缺该核心根的评价记录"})
            continue
        if (record.get("unknown") is True or record.get("d_point") is None
                or record.get("d_low") is None):
            gaps.append({"sub_scenario": sub, "opponent_mix": mix, "root_id": root_id,
                         "reason": "该核心根的评价未分辨/缺配对差（不合格）"})
    return gaps


# ===========================================================================
# P1（Lead 转达 P12 实测，2026-09-18）· 核心根缺失集合 = **冻结清单逐键覆盖**
#
# 缺陷（P9c 证据副本，只读复算）：挑战者 544f7d35… 的核心根边 **0/16 完成**、
# 缺 8 个核心根 / 32 桌；而生产自报 family_fill.missing 只有 **7** 条——少的正是
# branch_open|H|root000。根因有两层：
#   ① 缺失集合由"epoch 根 + 刷新批"这两个**当时的行集合**推出（_phase_missing 只在
#      该行集合里找根），既不是冻结清单、也带"行数"口径 ⇒ 不在该行集合里的核心根
#      永远报不出来（评审 G2：不得以数量补齐）；
#   ② 覆盖判据是"该 (子场景, 情景, 根) 有没有**一条记录**"（family_cell_lookup），
#      不看该记录是否合格、也不看是哪一臂/哪个情景的——同一根的多条记录会互相顶掉。
# 修法（本模块，production 侧）：
#   - 需求集合 = **冻结核心根清单**（archive/family-core-roots.json，一次冻结、只读；
#     本次推导与冻结件不一致即记冲突，不静默改用"当前内容"）；
#   - 覆盖按**精确键**（子场景 × 情景 × 根序号 × 面板种子 × 实际种子 × 根身份 × 臂）
#     逐项判定：多行证据取**并集**（any-complete），互不顶掉；
#   - 与生产自报的 missing 做**对照表**（逐键覆盖 vs 自报），差集逐条列出；
#   - 工作项用逐键缺失集合（冻结推导 ∪ 自报，差额具名），不用自报的计数口径。
# ===========================================================================

#: 冻结核心根清单 schema（需求集合；archive/family-core-roots.json）。
AV_FAMILY_CORE_LIST_SCHEMA = "sitin-av-family-core-roots/1"
#: 逐键覆盖表 schema（**完成读数**：补根调度收口时重算落盘）。
AV_FAMILY_CORE_COVERAGE_SCHEMA = "sitin-av-family-core-coverage/1"
#: 轮首**工作项快照** schema（P16-FU：它与完成读数分开落盘，名字不再混淆）。
AV_FAMILY_CORE_WORKITEM_SCHEMA = "sitin-av-family-core-coverage-workitem/1"
#: 完成读数文件名（archive/ 下）：补根调度收口时重算，代表"这一轮结束后覆盖到哪"。
AV_FAMILY_CORE_COVERAGE_FILENAME = "family-core-coverage.json"
#: 工作项快照文件名：轮首排评价用的临时读数，**不是**完成读数。
AV_FAMILY_CORE_WORKITEM_FILENAME = "family-core-coverage-workitem.json"
#: 臂集合（与执行侧同源：一次家族评价 = 基线臂 + 候选臂）。
AV_FAMILY_CORE_ARMS: Tuple[str, str] = ("baseline", "candidate")


def _av_family_core_key(row: Mapping[str, Any]) -> str:
    """核心根**精确键**（P1）：子场景 × 情景 × 根序号 × 面板种子 × 实际种子 × 根身份。"""

    return "{0}|{1}|idx{2:03d}|s{3}|seed{4}|{5}".format(
        str(row.get("sub_scenario") or ""), str(row.get("opponent_mix") or ""),
        int(row.get("root_index") or 0), row.get("panel_seed"),
        row.get("root_seed"), str(row.get("root_id") or ""))


#: 冻结核心根清单不可读 / 不合法 / 身份不符时的具名停因（停止并**保留原件**）。
AV_FAMILY_CORE_LIST_INVALID_STOP_REASON = "family_core_list_invalid_or_identity_mismatch"
#: 首次冻结写入失败时的具名停因（必需冻结件写不进去 ⇒ 不得继续）。
AV_FAMILY_CORE_LIST_WRITE_FAILED_STOP_REASON = "family_core_list_freeze_write_failed"
#: —— P16-FU（run7 实测）：首次冻结**必须来自完整核心矩阵声明** ——
#: 视图不完整（有格缺根）时**不落盘**（可后补），只记具名读数；把部分视图冻结成需求集合
#: 会让整个运行按"只缺这一格/这一根"继续（run7：冻结件只有 branch_open|H|idx000）。
AV_FAMILY_CORE_LIST_DEFERRED_VIEW_CODE = "family_core_list_freeze_deferred_incomplete_view"
#: 已有冻结件与**完整视图**推导不一致 ⇒ 具名拒绝（不得覆盖、不得运行中重定需求集合）。
AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON = "family_core_list_conflict_new_run_identity_required"


class FamilyCoreListRefused(RuntimeError):
    """冻结核心根清单不可用：**具名停止**（保留原件；运行中不得重定需求集合）。

    P16-C5：旧实现把"JSON 不可解析 / schema 或 channel 不符 / 文件不存在"三种情形
    走同一个重建分支，且写入 OSError 被吞——一个坏清单会被**覆盖**成当前推导清单，
    返回 source=derived、conflicts=[]，等于运行中偷偷重定义了需求集合。现在只有
    **明确首次初始化且文件不存在**才创建；已有文件不可读、不合法或身份不符即停止。
    """

    def __init__(self, message: str, *, stop_reason: str,
                 path: Optional[Path] = None,
                 problems: Sequence[Mapping[str, Any]] = ()) -> None:
        super().__init__(message)
        self.stop_reason = str(stop_reason)
        self.path = (None if path is None else str(path))
        self.problems = [dict(item) for item in problems]


def _av_family_core_list_problem(code: str, path: Path, reason: str) -> Dict[str, Any]:
    return {"code": code, "path": str(path), "reason": reason}


def _av_family_core_row(root_id: Any, *, sub_scenario: Any,
                        opponent_mix: Any) -> Dict[str, Any]:
    """一个核心根 → 冻结清单行（身份五维 + 实际种子 + 精确键；**唯一**构造点）。

    登记表推导与 epoch 核心根补齐都走这里，避免两处各写一套行形状（漂移即漏键）。
    """

    fields = av_family_root_identity_fields(root_id) or {}
    row: Dict[str, Any] = {
        "root_id": str(root_id), "sub_scenario": str(sub_scenario),
        "opponent_mix": str(opponent_mix),
        "root_index": (fields.get("root_index")
                       if fields.get("root_index") is not None else None),
        "panel_seed": fields.get("panel_seed"), "generator": fields.get("generator")}
    if row["root_index"] is not None and row["panel_seed"] is not None:
        row["root_seed"] = av_family_root_seed(
            prefix_source=("v2_behavior"
                           if str(row["generator"]).startswith("v2-behavior")
                           else "scripted_fixture"),
            sub_scenario=row["sub_scenario"], opponent_mix=row["opponent_mix"],
            panel_seed=row["panel_seed"], root_index=row["root_index"])
    else:
        row["root_seed"] = None
    row["key"] = _av_family_core_key(row)
    return row


def _av_family_core_list_frozen_shape(rows: Sequence[Mapping[str, Any]],
                                      channel: str) -> Dict[str, Any]:
    """冻结件的**结构完整性**读数：逐格配额（channel 的子场景侧 × 对手情景）。

    P16-FU：判定"冻结件是否缺根"必须看**结构**（每格 AV_FAMILY_CORE_ROOTS_PER_CELL
    根、格集合与矩阵一致），不能看"推导集是否逐字相同"——登记表会随运行增长
    （刷新批/指定旧根陆续登记），而"每格取排序前 N 根"的推导会随之位移（实测 r8/p7c
    家族换席流程：同格新增 s12 的根后推导集变化，但冻结件本身 8 根齐备）。run7 的
    冻结件则是**结构不完整**（4 格只填了 1 格、只有 1 根）。
    """

    per_cell: Dict[str, int] = {}
    for row in rows or ():
        key = "{0}|{1}".format(row.get("sub_scenario"), row.get("opponent_mix"))
        per_cell[key] = per_cell.get(key, 0) + 1
    required = ["{0}_{1}|{2}".format(channel, side, mix)
                for side in AV_FAMILY_SIDES
                for mix in av_archive().OPPONENT_MIXES]
    missing = sorted(cell for cell in required
                     if per_cell.get(cell, 0) < AV_FAMILY_CORE_ROOTS_PER_CELL)
    uncovered = sorted(cell for cell in required if per_cell.get(cell, 0) < 1)
    unexpected = sorted(cell for cell in per_cell if cell not in required)
    return {"complete": (not missing and not unexpected),        # 逐格配额齐全
            # 格覆盖齐全（每格至少 1 根）：**需求集合可用性**的判据——epoch 是通道的
            # 核心根声明，声明几根就以几根为需求集合；配额不足如实记 quota_complete。
            "cells_complete": (not uncovered and not unexpected),
            "quota_complete": (not missing and not unexpected),
            "per_cell": dict(sorted(per_cell.items())),
            "required_cells": required, "missing_cells": missing,
            "uncovered_cells": uncovered,
            "unexpected_cells": unexpected,
            "required_per_cell": AV_FAMILY_CORE_ROOTS_PER_CELL}


def _av_family_core_list_unregistered(rows: Sequence[Mapping[str, Any]],
                                      registry: Mapping[str, Any]) -> List[str]:
    """冻结件里**已不在登记表**的根标识（身份消失：真冲突）。"""

    known = {str(item) for item in (registry.get("roots") or ())}
    return sorted(str(row.get("root_id")) for row in rows or ()
                  if str(row.get("root_id")) not in known)


def av_family_core_root_list(*, channel: str, registry: Mapping[str, Any],
                             freeze_path: Optional[Path] = None,
                             epoch_rows: Optional[Sequence[Mapping[str, Any]]] = None
                             ) -> Dict[str, Any]:
    """冻结核心根清单（**需求集合**）：一次冻结、逐键固定、运行中不得改写。

    **P16-FU 明文规则（run7 实测后收紧）**：

    ① 首次冻结**只在需求集合完整时**发生：需求集合 = 逐格取登记表已登记的核心根，
       不足配额时用**通道 epoch 的核心根声明**（epoch_rows）补齐（完整 = 4 格 ×
       AV_FAMILY_CORE_ROOTS_PER_CELL 根）。仍不完整时**不落盘**（返回 source=derived、
       created=False、view_complete=False + 具名 deferred 读数）——部分视图冻结成需求
       集合会让整个运行按"只缺这一格"继续（run7：冻结件只有 branch_open|H|idx000）；
    ② 冻结后运行时**只读**：已有文件必须可读、可解析、schema 与 channel 相符、行合法，
       否则 FamilyCoreListRefused（停因 AV_FAMILY_CORE_LIST_INVALID_STOP_REASON），
       保留原件、绝不覆盖重写；
    ③ 已有冻结件与**完整视图**推导的集合不一致（键集合不同）⇒ **具名拒绝**，
       停因 AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON：运行中不得重定需求集合，
       要换需求集合就换运行身份（新运行目录）；视图不完整时不做该判定（此时推导集
       本就不全），只把差额记进 conflicts 供核对；
    ④ 首次冻结写入失败不吞异常（必需冻结件写不进去即停止）。
    """

    # 需求集合 = **完整核心矩阵声明**：逐格先取登记表已登记的核心根，不足配额时用
    # **通道 epoch 的核心根声明**补齐（P16-FU：登记表是"当前已物化"的视图，epoch 才是
    # 该通道的核心根声明；只看登记表会在"核心根还没登记齐"时冻结出部分需求集合——
    # run7 的 1 根冻结件正是这么来的）。
    derived: List[Dict[str, Any]] = []
    matrix = _av_family_core_matrix(channel, registry)
    epoch_by_cell: Dict[str, List[str]] = {}
    for row in (epoch_rows or ()):
        if not isinstance(row, Mapping):
            continue
        root_id = str(row.get("root_id") or "")
        if not root_id:
            continue
        cell = "{0}|{1}".format(row.get("sub_scenario"), row.get("opponent_mix"))
        if root_id not in epoch_by_cell.setdefault(cell, []):
            epoch_by_cell[cell].append(root_id)
    for cell in matrix["cells"].values():
        chosen = [str(root_id) for root_id in
                  cell["roots"][:AV_FAMILY_CORE_ROOTS_PER_CELL]]
        cell_key = "{0}|{1}".format(cell["sub_scenario"], cell["opponent_mix"])
        for root_id in epoch_by_cell.get(cell_key, ()):
            if len(chosen) >= AV_FAMILY_CORE_ROOTS_PER_CELL:
                break
            if root_id not in chosen:
                chosen.append(root_id)
        for root_id in chosen:
            derived.append(_av_family_core_row(root_id,
                                              sub_scenario=cell["sub_scenario"],
                                              opponent_mix=cell["opponent_mix"]))
    path = (None if freeze_path is None else Path(freeze_path))
    source = "derived"
    created = False
    frozen_at_utc: Optional[str] = None
    conflicts: List[Dict[str, Any]] = []
    deferred: Optional[Dict[str, Any]] = None
    view_complete = bool(matrix["complete"])
    rows = derived
    if path is None:
        # 调用方没有要求冻结件：如实标注 derived（不落盘、不改需求集合）。
        return {"schema": AV_FAMILY_CORE_LIST_SCHEMA, "channel": channel,
                "source": source, "created": False, "frozen_at_utc": None,
                "roots": rows, "conflicts": conflicts, "path": None,
                "n_roots": len(rows), "matrix_complete": view_complete,
                "view_complete": view_complete, "deferred": None,
                "missing_cells": [dict(item) for item in matrix["missing"]]}
    if path.exists():
        # —— 已有文件（含同名目录等异常占位）：只读。不可读 / 不可解析 / schema 或
        #    channel 不符 / 行不合法 一律具名停止（保留原件，绝不覆盖重写需求集合）。——
        problems: List[Dict[str, Any]] = []
        try:
            if not path.is_file():
                raise OSError("同名路径不是普通文件（{0}）".format(
                    "目录" if path.is_dir() else "其他类型"))
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            problems.append(_av_family_core_list_problem(
                "frozen_core_list_unreadable", path,
                "冻结核心根清单不可读（{0}）：保留原件、停止——不得重建需求集合".format(
                    error)))
            text = None
        frozen: Optional[Mapping[str, Any]] = None
        if text is not None:
            try:
                parsed = json.loads(text)
            except ValueError as error:
                problems.append(_av_family_core_list_problem(
                    "frozen_core_list_invalid_json", path,
                    "冻结核心根清单不是合法 JSON（{0}）：保留原件、停止——不得按当前"
                    "推导重写（一次冻结、运行中只读）".format(error)))
                parsed = None
            if parsed is not None:
                if not isinstance(parsed, Mapping):
                    problems.append(_av_family_core_list_problem(
                        "frozen_core_list_not_mapping", path,
                        "冻结核心根清单顶层不是映射：保留原件、停止"))
                else:
                    frozen = parsed
        if frozen is not None and not problems:
            if str(frozen.get("schema")) != AV_FAMILY_CORE_LIST_SCHEMA:
                problems.append(_av_family_core_list_problem(
                    "frozen_core_list_schema_mismatch", path,
                    "冻结核心根清单 schema 不符（{0!r} != {1!r}）：身份不符即停止，"
                    "保留原件".format(frozen.get("schema"), AV_FAMILY_CORE_LIST_SCHEMA)))
            if str(frozen.get("channel") or "") != str(channel):
                problems.append(_av_family_core_list_problem(
                    "frozen_core_list_channel_mismatch", path,
                    "冻结核心根清单 channel 不符（{0!r} != {1!r}）：身份不符即停止，"
                    "保留原件".format(frozen.get("channel"), channel)))
            frozen_rows = [dict(item) for item in (frozen.get("roots") or ())
                           if isinstance(item, Mapping)]
            invalid_rows = [
                index for index, item in enumerate(frozen.get("roots") or ())
                if not isinstance(item, Mapping) or not str(item.get("root_id") or "")
                or not str(item.get("key") or "")]
            if invalid_rows:
                problems.append(_av_family_core_list_problem(
                    "frozen_core_list_row_invalid", path,
                    "冻结核心根清单第 {0} 行不合法（缺 root_id/key）：停止，保留原件".format(
                        invalid_rows)))
            if len(frozen_rows) != len(list(frozen.get("roots") or ())):
                problems.append(_av_family_core_list_problem(
                    "frozen_core_list_row_invalid", path,
                    "冻结核心根清单有非映射行：停止，保留原件"))
        if problems:
            raise FamilyCoreListRefused(
                "冻结核心根清单不可用（停止并保留原件）：{0}".format(
                    "；".join(str(item["reason"]) for item in problems)),
                stop_reason=AV_FAMILY_CORE_LIST_INVALID_STOP_REASON,
                path=path, problems=problems)
        assert frozen is not None
        rows = frozen_rows
        source = "frozen"
        frozen_at_utc = (str(frozen.get("frozen_at_utc"))
                         if frozen.get("frozen_at_utc") else None)
        derived_keys = {item.get("key") for item in derived}
        frozen_keys = {item.get("key") for item in rows}
        shape = _av_family_core_list_frozen_shape(rows, channel)
        derived_shape = _av_family_core_list_frozen_shape(derived, channel)
        unregistered = _av_family_core_list_unregistered(rows, registry)
        if derived_keys != frozen_keys or not shape["complete"] or unregistered:
            # ③ 明文规则：冻结件**结构缺根**（逐格配额不足/多出矩阵外格）**而当前声明
            #    （登记表 + epoch 核心根）已能给出完整集合** ⇒ 具名拒绝、要求新运行身份
            #    （run7 形态：1 根冻结件 vs 8 根核心矩阵）。
            #    其余差异只记**具名读数**（不拒绝、更不覆盖）：
            #      - 成员位移：登记表随运行增长，而"每格取排序前 N 根"的推导会随之位移
            #        （实测 r8/p7c 家族换席流程）；需求集合仍以**冻结件**为准（一次冻结、
            #        只读），差额逐条列出供核对；
            #      - 冻结件里的根暂时未登记：epoch 声明的核心根可能尚未物化（补根层负责），
            #        同样只记读数；
            #      - 当前声明也给不出完整集合（视图不完整）：此时没有更好的需求集合可用，
            #        保持冻结件 + 记差额。
            detail = {
                "channel": channel,
                "frozen_only": sorted(str(k) for k in frozen_keys - derived_keys),
                "derived_only": sorted(str(k) for k in derived_keys - frozen_keys),
                "frozen_n_roots": len(rows), "derived_n_roots": len(derived),
                "frozen_shape": shape, "derived_shape": derived_shape,
                "unregistered_roots": unregistered}
            if derived_shape["cells_complete"] and not shape["cells_complete"]:
                raise FamilyCoreListRefused(
                    "冻结核心根清单**结构缺根**（frozen {0} 根，缺格 {1}），而登记表 + "
                    "epoch 核心根声明已能给出完整集合（{2} 根）：运行中不得重定需求集合，"
                    "具名拒绝并要求新运行身份（{3}）".format(
                        len(rows), shape["missing_cells"], len(derived),
                        AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON),
                    stop_reason=AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON, path=path,
                    problems=[dict(detail, code="frozen_core_list_conflicts_with_derived",
                                   reason=("冻结件结构缺根而当前声明完整：保留原件、具名停止；"
                                           "要换需求集合必须新开运行身份（不得覆盖重写）"))])
            conflicts.append(dict(
                detail,
                code=("frozen_core_list_membership_delta" if shape["complete"]
                      else "frozen_core_list_incomplete_both_sides"),
                reason=("冻结件结构齐备但推导集成员位移（登记表增长）：需求集合仍以**冻结件**"
                        "为准，差额逐条列出供核对" if shape["complete"] else
                        "冻结件与当前声明都不完整（缺格 {0}）：以**冻结件**为需求集合，"
                        "差额逐条列出供核对".format(shape["missing_cells"]))))
    else:
        # —— 唯一允许创建的情形：明确首次初始化（文件不存在）+ **需求集合完整** ——
        derived_shape = _av_family_core_list_frozen_shape(derived, channel)
        if not derived_shape["cells_complete"]:
            # 部分视图**不落盘**：冻结件是运行期需求集合，绝不能只有一格/一根。
            deferred = {
                "code": AV_FAMILY_CORE_LIST_DEFERRED_VIEW_CODE,
                "n_roots_in_view": len(derived),
                "missing_cells": [dict(item) for item in matrix["missing"]],
                "shape": derived_shape,
                "reason": ("首次冻结要求**完整核心矩阵声明**（{0} 格 × {1} 根）："
                           "登记表 + epoch 核心根声明合计只有 {2} 根、缺格 {3}——本轮"
                           "不冻结（不落部分视图），补齐后再冻结；本轮仍按当前推导读取"
                           "（不因此改写需求集合）").format(
                               len(matrix["cells"]), AV_FAMILY_CORE_ROOTS_PER_CELL,
                               len(derived), derived_shape["missing_cells"])}
            return {"schema": AV_FAMILY_CORE_LIST_SCHEMA, "channel": channel,
                    "source": source, "created": False, "frozen_at_utc": None,
                    "roots": rows, "conflicts": conflicts, "path": str(path),
                    "n_roots": len(rows), "matrix_complete": False,
                    "view_complete": False, "deferred": deferred,
                    "missing_cells": [dict(item) for item in matrix["missing"]]}
        payload = {"schema": AV_FAMILY_CORE_LIST_SCHEMA, "channel": channel,
                   "frozen_at_utc": utc_now(), "roots": derived,
                   "note": ("核心根清单在补根调度前**冻结**：此后本文件只读，"
                            "缺失集合一律按它逐键推导（不数登记行数）")}
        try:
            av_atomic_write_json(path, payload)
        except OSError as error:
            # 必需冻结件写不进去 ⇒ 具名停止（不"当作没有清单"继续跑）。
            raise FamilyCoreListRefused(
                "首次冻结核心根清单写入失败（{0}）：必需冻结件写不进去即停止".format(error),
                stop_reason=AV_FAMILY_CORE_LIST_WRITE_FAILED_STOP_REASON,
                path=path,
                problems=[_av_family_core_list_problem(
                    "frozen_core_list_write_failed", path,
                    "首次冻结写入失败：{0}".format(error))]) from error
        created = True
        frozen_at_utc = str(payload["frozen_at_utc"])
    requirement_shape = _av_family_core_list_frozen_shape(rows, channel)
    return {"schema": AV_FAMILY_CORE_LIST_SCHEMA, "channel": channel,
            "source": source, "created": created, "frozen_at_utc": frozen_at_utc,
            "roots": rows, "conflicts": conflicts, "path": str(path),
            "n_roots": len(rows), "matrix_complete": view_complete,
            "view_complete": view_complete, "deferred": deferred,
            # 需求集合（本函数返回的 roots）是否完整：登记表视图 + epoch 声明两者分开报，
            # 调用方据此区分"登记表还没物化齐"与"需求集合本身缺根"。
            "requirement_complete": bool(requirement_shape["cells_complete"]),
            "requirement_quota_complete": bool(requirement_shape["quota_complete"]),
            "requirement_shape": requirement_shape,
            "missing_cells": [dict(item) for item in matrix["missing"]]}


def _av_family_evaluation_products(run_root: Path) -> List[Dict[str, Any]]:
    """家族根评价产物逐条（**唯一**的臂级覆盖依据：不数登记行数）。

    两种落盘形态都认：完整运行目录 iterations/iter-*/family/*/evaluation.json；
    证据副本目录 family/*.json（文件名形如 iter-02__<cid>-<cell>-<mix>-….json）。

    P16-C1：这里收的是**完整评价身份**（候选 × 子场景 × 情景 × 来源根标识 × 根序号
    × 面板种子 × 实际种子 × 生成器 × 座位 × 臂 × 执行/准入读数）。旧实现只收
    （候选、子场景、情景、根序号、臂），于是"同序号不同根/不同种子/不同生成器"
    的产物会被算成已完成重评——覆盖判定不得再用这种稀疏键。
    """

    root = Path(run_root)
    paths: List[Path] = []
    for iter_dir in sorted(root.glob("iterations/iter-*")):
        paths.extend(sorted((iter_dir / "family").glob("*/evaluation.json")))
        # 条件通道的同根评价也是该（候选 × 根 × 臂）的可核证据：作为**具名次级**
        # 依据收进来（basis 会写清来自哪个通道），不冒充家族通道产物。
        paths.extend(sorted((iter_dir / "conditional").glob("*/evaluation.json")))
    paths.extend(sorted((root / "family").glob("*.json")))
    out: List[Dict[str, Any]] = []
    for path in paths:
        channel = "family" if path.parent.name == "family" or "/family/" in str(path) \
            else "conditional"
        payload = _load_json_file(path)
        if not isinstance(payload, Mapping):
            continue
        identity = payload.get("identity") or {}
        panel = payload.get("panel") or {}
        candidate_id = str(identity.get("candidate_id") or "")
        admission = payload.get("result_admission")
        admission_ok = (bool(admission.get("ok"))
                        if isinstance(admission, Mapping) else None)
        for sample in (payload.get("samples") or ()):
            if not isinstance(sample, Mapping):
                continue
            arms = dict(sample.get("arms") or {})
            descriptor = sample.get("root_descriptor")
            descriptor = dict(descriptor) if isinstance(descriptor, Mapping) else {}
            # 座位：产物自报的焦点座位（样本级优先，其次面板级）；都没有即 None
            # （**不是**用根序号兜底：None 只影响 seat_basis 读数，不进身份兜底）。
            seat = sample.get("focal_anchor_seat")
            seat_source = "sample"
            if seat is None:
                seat = panel.get("focal_seat")
                seat_source = "panel" if seat is not None else None
            arm_candidates = {name: (str((block or {}).get("candidate_id") or "") or None)
                              for name, block in arms.items()
                              if isinstance(block, Mapping)}
            problems: List[str] = []
            if candidate_id and str(sample.get("candidate_id") or "") not in ("", candidate_id):
                problems.append("样本候选身份与评价身份不一致（{0} != {1}）".format(
                    sample.get("candidate_id"), candidate_id))
            sample_mix = sample.get("opponent_mix")
            if (sample_mix not in (None, "") and identity.get("opponent_mix") not in (None, "")
                    and str(sample_mix) != str(identity.get("opponent_mix"))):
                problems.append("样本情景与评价身份情景不一致")
            sample_sub = sample.get("scenario")
            if (sample_sub not in (None, "") and panel.get("predicate") not in (None, "")
                    and str(sample_sub) != str(panel.get("predicate"))):
                problems.append("样本子场景与面板子场景不一致")
            panel_seed = panel.get("panel_seed")
            if (descriptor.get("panel_seed") is not None and panel_seed is not None
                    and int(descriptor["panel_seed"]) != int(panel_seed)):
                problems.append("根描述符面板种子与面板块不一致")
            if (descriptor.get("root_id") is not None
                    and str(descriptor.get("root_id"))
                    != str(sample.get("source_root_id"))):
                problems.append("根描述符标识与样本来源根标识不一致")
            for name in ("root_index", "root_seed"):
                declared = sample.get(name)
                from_descriptor = descriptor.get(name)
                if (declared is not None and from_descriptor is not None
                        and int(declared) != int(from_descriptor)):
                    problems.append("样本 {0} 与根描述符不一致".format(name))
            out.append({
                "path": str(path), "channel": channel,
                "candidate_id": candidate_id,
                "source_root_id": sample.get("source_root_id"),
                "sub_scenario": sample.get("scenario"),
                "opponent_mix": sample.get("opponent_mix"),
                "root_index": sample.get("root_index"),
                "root_seed": sample.get("root_seed"),
                "panel_seed": (descriptor.get("panel_seed")
                               if descriptor.get("panel_seed") is not None else panel_seed),
                "generator": (descriptor.get("generator") or panel.get("generator")),
                # 产物**自报**的面板块读数（与根描述符分开留：两者都可与来源根身份
                # 交叉核对，合并成一个字段就查不出"面板块自报生成器不符"）。
                "panel_generator": panel.get("generator"),
                "panel_seed_declared": panel_seed,
                "seat": (None if seat is None else int(seat)),
                "seat_source": seat_source,
                "arm_candidates": arm_candidates,
                "evaluation_id": identity.get("evaluation_id"),
                "execution_kind": payload.get("execution_kind"),
                "runtime_kind": payload.get("runtime_kind"),
                "selection_eligible": payload.get("selection_eligible"),
                "admission_ok": admission_ok,
                "requirement_digest": sample.get("root_requirement_digest"),
                "identity_problems": problems,
                "ok": bool(payload.get("ok")),
                "arms_complete": (all(
                    str((block or {}).get("status")) == "complete"
                    and bool((block or {}).get("usable"))
                    for block in arms.values()) and len(arms) == 2),
                "arms": sorted(arms),
                "root_content_digest": sample.get("root_content_digest")})
    return out


#: 家族核心根边的**焦点座位**（通道契约固定值，唯一来源）：家族条件评价在单根条件
#: 面板里 focal_seat=0（见 _av_family_expected_instances 与 run_av_evaluation 的
#: 单根面板调用）。产物自报座位与本值不符即不采用；产物未自报座位时按本契约接受
#: 并在 basis 里具名 seat_basis（**不是**用根序号兜底身份）。
AV_FAMILY_CORE_ANCHOR_SEAT = 0


def _av_family_record_candidates(rows: Mapping[str, Any], mix: Any,
                                 root_id: Any) -> List[Mapping[str, Any]]:
    """同一根在本子场景下的**全部**候选记录（情景限定键 + 裸键），不互相顶掉。

    裸键记录必须自带同情景声明才算数（opponent_mix 不符即不是本情景的证据）——
    旧实现只取第一条命中，跨情景/历史记录会把真正的缺失顶掉。

    P16-C1：记录级回退的**可信条件**（缺一不可）：
      ① 记录必须挂在**完整根身份键**上（情景限定格键 family_cell_key(mix, root_id)
         或裸 root_id 且自带同情景声明）——按根序号或行数匹配一律不作数；
      ② 记录合格（未分辨/缺配对差不合格）；
      ③ 记录**自报**的身份字段（root_id/source_root_id/root_seed/panel_seed/generator/
         candidate_id）不得与需求冲突（声明了就必须逐字一致；没声明即按键身份接受）。
    """

    if not isinstance(rows, Mapping):
        return []
    archive_mod = av_archive()
    keys = [archive_mod.family_cell_key(mix, root_id), str(root_id)]
    out: List[Mapping[str, Any]] = []
    seen = set()
    for key in keys:
        record = rows.get(key)
        if not isinstance(record, Mapping) or id(record) in seen:
            continue
        seen.add(id(record))
        declared = record.get("opponent_mix")
        if (key == str(root_id) and declared not in (None, "")
                and str(declared) != str(mix)):
            continue                    # 裸键但声明了别的情景：不是本情景的证据
        out.append(record)
    return out


def _av_family_record_identity_problems(record: Mapping[str, Any],
                                        root: Mapping[str, Any]) -> List[str]:
    """记录自报身份与需求根的**冲突**读数（只报冲突，不把"没声明"当冲突）。"""

    problems: List[str] = []
    declared_root = record.get("source_root_id") or record.get("root_id")
    if declared_root not in (None, "") and str(declared_root) != str(root.get("root_id")):
        problems.append("记录自报根标识与需求根不符（{0} != {1}）".format(
            declared_root, root.get("root_id")))
    for name in ("root_seed", "panel_seed", "root_index"):
        declared = record.get(name)
        wanted = root.get(name)
        if declared is None or wanted is None:
            continue
        try:
            mismatch = int(declared) != int(wanted)
        except (TypeError, ValueError):
            mismatch = str(declared) != str(wanted)
        if mismatch:
            problems.append("记录自报{0}与需求根不符（{1} != {2}）".format(
                name, declared, wanted))
    declared_generator = record.get("generator")
    if (declared_generator not in (None, "") and root.get("generator") not in (None, "")
            and str(declared_generator) != str(root.get("generator"))):
        problems.append("记录自报生成器与需求根不符（{0} != {1}）".format(
            declared_generator, root.get("generator")))
    return problems


def _av_family_product_matches_root(item: Mapping[str, Any], root: Mapping[str, Any],
                                    arm: str, candidate_id: str
                                    ) -> Tuple[bool, str, Dict[str, Any]]:
    """一条臂级产物是否**确实是**该（候选 × 完整根身份 × 座位 × 臂）的可核评价。

    P16-C1 判据（缺任一即不覆盖，缺关键身份**不得用根序号兜底**）：
      ① 结果准入：评价产物 ok=True（被拒产物不得充当覆盖证据）；
      ② 候选身份：产物候选 = 需求候选（并核对臂自报候选：候选臂=本候选、
         基线臂=固定基线标识；臂未自报候选时按"未声明"如实记 basis，不冒充）；
      ③ 来源根标识：必须**逐字**等于需求根身份（空/缺即不采用）；
      ④ 实际种子：产物实际执行种子必须等于需求根的实际种子（缺任一即不采用）；
      ⑤ 子场景 / 对手情景 / 根序号：逐字相等；
      ⑥ 面板种子 / 生成器：与**来源根身份解析出的**五个维度交叉核对（产物自报
         面板块不一致即不采用）；
      ⑦ 座位：产物自报座位必须等于家族通道固定焦点座位；未自报时按该契约接受
         并在 basis 里具名 seat_basis；
      ⑧ 臂：该臂在该产物里齐备（arms_complete：两臂 complete 且 usable）。
    """

    reasons: List[str] = []
    basis: Dict[str, Any] = {}
    if item.get("ok") is not True:
        return False, "评价产物未被准入（ok=False/缺失）：不采用", basis
    if str(item.get("candidate_id") or "") != str(candidate_id):
        return False, "候选身份不符（{0} != {1}）：不采用他者结果".format(
            item.get("candidate_id"), candidate_id), basis
    if item.get("identity_problems"):
        return False, "评价产物自报身份自相矛盾：{0}".format(
            "；".join(str(x) for x in item["identity_problems"])), basis
    source_root_id = str(item.get("source_root_id") or "")
    root_id = str(root.get("root_id") or "")
    if not source_root_id or not root_id:
        return False, "缺来源根标识（产物 {0!r} / 需求 {1!r}）：不得用根序号兜底".format(
            item.get("source_root_id"), root.get("root_id")), basis
    if source_root_id != root_id:
        return False, "来源根标识不符（{0} != {1}）：不是同一个根".format(
            source_root_id, root_id), basis
    if str(item.get("sub_scenario")) != str(root.get("sub_scenario")):
        return False, "子场景不符（{0} != {1}）".format(
            item.get("sub_scenario"), root.get("sub_scenario")), basis
    if str(item.get("opponent_mix")) != str(root.get("opponent_mix")):
        return False, "对手情景不符（{0} != {1}）".format(
            item.get("opponent_mix"), root.get("opponent_mix")), basis
    wanted_seed = root.get("root_seed")
    actual_seed = item.get("root_seed")
    if wanted_seed is None or actual_seed is None:
        return False, "缺实际种子（需求 {0!r} / 产物 {1!r}）：不得用根序号兜底".format(
            wanted_seed, actual_seed), basis
    if int(actual_seed) != int(wanted_seed):
        return False, "实际种子不符（产物 {0} != 需求 {1}）：不是同一座牌山".format(
            actual_seed, wanted_seed), basis
    wanted_index = root.get("root_index")
    if wanted_index is None or item.get("root_index") is None:
        return False, "缺根序号（需求 {0!r} / 产物 {1!r}）：身份不完整".format(
            wanted_index, item.get("root_index")), basis
    if int(item["root_index"]) != int(wanted_index):
        return False, "根序号不符（产物 {0} != 需求 {1}）".format(
            item["root_index"], wanted_index), basis
    parsed = av_family_root_identity_fields(root_id)
    if parsed is not None:
        basis["identity_basis"] = "v2_root_identity"
        for name in ("sub_scenario", "opponent_mix", "panel_seed", "root_index"):
            declared = root.get(name)
            if declared is None:
                continue
            if str(declared) != str(parsed[name]):
                reasons.append("需求根的 {0} 与其根身份的 {1} 不一致".format(
                    name, parsed[name]))
        wanted_panel_seed = root.get("panel_seed")
        if wanted_panel_seed is not None and int(wanted_panel_seed) != int(parsed["panel_seed"]):
            reasons.append("面板种子不符（需求 {0} != 根身份 {1}）".format(
                wanted_panel_seed, parsed["panel_seed"]))
        wanted_generator = root.get("generator")
        if wanted_generator not in (None, "") and str(wanted_generator) != str(parsed["generator"]):
            reasons.append("生成器不符（需求 {0} != 根身份 {1}）".format(
                wanted_generator, parsed["generator"]))
        declared_panel_seed = item.get("panel_seed")
        if declared_panel_seed is not None and int(declared_panel_seed) != int(parsed["panel_seed"]):
            reasons.append("产物自报面板种子与来源根身份不符（{0} != {1}）".format(
                declared_panel_seed, parsed["panel_seed"]))
        declared_generator = item.get("panel_generator")
        if (declared_generator not in (None, "")
                and str(declared_generator) != str(parsed["generator"])):
            reasons.append("产物自报生成器与来源根身份不符（{0} != {1}）".format(
                declared_generator, parsed["generator"]))
        declared_panel_seed = item.get("panel_seed_declared")
        if (declared_panel_seed is not None
                and int(declared_panel_seed) != int(parsed["panel_seed"])):
            reasons.append("产物自报面板种子与来源根身份不符（{0} != {1}）".format(
                declared_panel_seed, parsed["panel_seed"]))
        if int(item["root_index"]) != int(parsed["root_index"]):
            reasons.append("产物根序号与来源根身份不符（{0} != {1}）".format(
                item["root_index"], parsed["root_index"]))
        basis["root_identity_fields"] = {key: parsed[key] for key in (
            "generator", "sub_scenario", "opponent_mix", "panel_seed", "root_index")}
    else:
        # 旧（v1）根身份：没有可解析的五维，但必须**逐字**匹配同一根标识 + 实际种子
        # （仍然不是按序号兜底），并如实具名身份依据。
        basis["identity_basis"] = "legacy_root_id_exact"
    if reasons:
        return False, "评价产物与需求根身份不符：{0}".format("；".join(reasons)), basis
    seat = item.get("seat")
    if seat is not None and int(seat) != int(AV_FAMILY_CORE_ANCHOR_SEAT):
        return False, "座位不符（产物 {0} != 家族通道焦点座位 {1}）".format(
            seat, AV_FAMILY_CORE_ANCHOR_SEAT), basis
    basis["seat_basis"] = ("product_declared:{0}".format(item.get("seat_source"))
                           if seat is not None else "family_contract_anchor_seat")
    if arm not in (item.get("arms") or ()):
        return False, "产物不含该臂（{0}）".format(arm), basis
    if not item.get("arms_complete"):
        return False, "两臂未齐备（arms_complete=False）：该臂不构成可核评价", basis
    declared_arm_candidate = (item.get("arm_candidates") or {}).get(arm)
    if declared_arm_candidate is not None:
        expected_arm_candidate = (AV_BASELINE_ID if str(arm) == "baseline"
                                  else str(candidate_id))
        if str(declared_arm_candidate) != expected_arm_candidate:
            return False, "臂自报候选身份不符（{0} 臂 {1} != {2}）".format(
                arm, declared_arm_candidate, expected_arm_candidate), basis
        basis["arm_identity_basis"] = "arm_declared_candidate"
    else:
        basis["arm_identity_basis"] = "arm_candidate_not_declared"
    return True, "", basis


def av_family_core_coverage(*, core_rows: Sequence[Mapping[str, Any]],
                            entry: Optional[Mapping[str, Any]],
                            candidate_id: str,
                            products: Optional[Sequence[Mapping[str, Any]]] = None,
                            arms: Sequence[str] = AV_FAMILY_CORE_ARMS) -> Dict[str, Any]:
    """**逐键覆盖**（冻结核心根清单 × 臂）：多行证据取并集，生产自报另记。

    每个键的覆盖判据（任一来源成立即覆盖，全部来源逐条留痕）：
      - 臂级：该候选在该根上有 arms_complete 的评价产物（最强证据）；
      - 记录级回退：归档记录合格（未分辨/缺配对差即不合格）——双臂配对差合格
        蕴含两臂都跑过可核评价，但本记录**不逐臂分列**，故 basis 如实标注。
    """

    evals = (entry or {}).get("family_evaluations") or {}
    product_rows = [item for item in (products or ())
                    if str(item.get("candidate_id") or "") == str(candidate_id)]
    keys: List[Dict[str, Any]] = []
    missing_tokens: List[str] = []
    missing_keys: List[str] = []
    rejected_products: List[Dict[str, Any]] = []
    for root in core_rows:
        sub = str(root.get("sub_scenario") or "")
        mix = str(root.get("opponent_mix") or "")
        root_id = str(root.get("root_id") or "")
        arm_rows: Dict[str, Dict[str, Any]] = {}
        for arm in arms:
            matched: List[Tuple[Mapping[str, Any], Dict[str, Any]]] = []
            rejected: List[Dict[str, Any]] = []
            for item in product_rows:
                ok, reason, basis = _av_family_product_matches_root(
                    item, root, str(arm), candidate_id)
                if ok:
                    matched.append((item, basis))
                else:
                    rejected.append({"path": item.get("path"), "channel": item.get("channel"),
                                     "reason": reason})
            family_matched = [item for item, _b in matched
                              if str(item.get("channel")) == "family"]
            arm_rows[str(arm)] = {
                "covered": bool(matched),
                "basis": (("family_evaluation_product:full_root_identity" if family_matched
                           else "conditional_channel_product:full_root_identity（同候选同根"
                                "同臂的可核评价；来自条件通道，basis 具名）")
                          if matched else None),
                "products": [item["path"] for item, _b in matched],
                "channels": sorted({str(item.get("channel")) for item, _b in matched}),
                "rejected_products": rejected,
                "identity_basis": sorted({str(basis.get("identity_basis")) for _i, basis in matched}),
                "seat_bases": sorted({str(basis.get("seat_basis")) for _i, basis in matched}),
                "arm_identity_bases": sorted({str(basis.get("arm_identity_basis"))
                                              for _i, basis in matched})}
            rejected_products.extend(dict(row, key="{0}|{1}|{2}".format(sub, mix, root_id))
                                     for row in rejected)
        records = _av_family_record_candidates(evals.get(sub) or {}, mix, root_id)
        usable_records = [record for record in records
                          if not (record.get("unknown") is True
                                  or record.get("d_point") is None
                                  or record.get("d_low") is None)
                          and not _av_family_record_identity_problems(record, root)]
        conflicting_records = [record for record in records
                               if _av_family_record_identity_problems(record, root)]
        for _arm, row in arm_rows.items():
            if not row["covered"] and usable_records:
                row["covered"] = True
                row["basis"] = ("paired_archive_record（记录级回退：挂在**完整根身份键**上、"
                                "配对差合格、且自报身份与需求根无冲突；不逐臂分列）")
        root_covered = all(row["covered"] for row in arm_rows.values())
        key = str(root.get("key") or _av_family_core_key(root))
        keys.append({
            "key": key, "root_id": root_id, "sub_scenario": sub,
            "opponent_mix": mix, "root_index": root.get("root_index"),
            "panel_seed": root.get("panel_seed"), "root_seed": root.get("root_seed"),
            "arms": arm_rows, "covered": root_covered,
            "records_seen": len(records), "records_usable": len(usable_records),
            "records_identity_conflicts": [
                {"problems": _av_family_record_identity_problems(record, root)}
                for record in conflicting_records],
            "uncovered_arms": sorted(arm for arm, row in arm_rows.items()
                                     if not row["covered"])})
        if not root_covered:
            missing_keys.append(key)
            missing_tokens.append("{0}|{1}|{2}".format(sub, mix, root_id))
    covered = [row for row in keys if row["covered"]]
    return {
        "schema": AV_FAMILY_CORE_COVERAGE_SCHEMA, "candidate_id": str(candidate_id),
        "n_roots": len(keys), "n_roots_covered": len(covered),
        "n_edges": len(keys) * len(tuple(arms)),
        "n_edges_covered": sum(1 for row in keys for arm_row in row["arms"].values()
                               if arm_row["covered"]),
        "keys": keys, "missing_keys": missing_keys,
        "missing_tokens": sorted(set(missing_tokens)),
        "rejected_products": rejected_products,
        "at_utc": utc_now(),
        "note": ("逐键覆盖（候选 × 子场景 × 情景 × **来源根标识** × 根序号 × 面板种子 × "
                 "实际种子 × 生成器 × 座位 × 臂）：由**冻结核心根清单**推导需求集合，"
                 "产物按完整根身份逐项核对（缺关键身份不得用根序号兜底），记录级回退"
                 "必须挂在完整根身份键上且自报身份无冲突；多行证据取并集（不互相顶掉），"
                 "不数登记行数")}


def _av_family_core_coverage_vs_reported(*, coverage: Mapping[str, Any],
                                         reported: Sequence[Any]) -> Dict[str, Any]:
    """逐键覆盖 与 生产自报 missing 的**对照表**（差集逐条列出）。"""

    frozen_tokens = sorted(str(token) for token in coverage.get("missing_tokens") or ())
    reported_tokens = sorted(str(token) for token in (reported or ()))
    return {
        "schema": AV_FAMILY_CORE_COVERAGE_SCHEMA,
        "frozen_missing": frozen_tokens, "reported_missing": reported_tokens,
        "both": sorted(set(frozen_tokens) & set(reported_tokens)),
        "frozen_only": sorted(set(frozen_tokens) - set(reported_tokens)),
        "reported_only": sorted(set(reported_tokens) - set(frozen_tokens)),
        "consistent": frozen_tokens == reported_tokens,
        "n_frozen": len(frozen_tokens), "n_reported": len(reported_tokens),
        "note": ("对照表：frozen_only 就是「生产自报少算」的那几条（旧判据按行集合推"
                 "缺失），reported_only 是不在冻结清单里的额外点名（保留、不静默丢弃）")}


def _av_family_refresh_batch(channel: str, declarations: Mapping[str, Any],
                             registry: Mapping[str, Any],
                             epoch: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]],
                                                                List[Dict[str, Any]]]:
    """声明批 → 家族刷新根行（已物化者）；未物化者交回补根层先评价。

    A2：去重按**完整根身份**（含生成器/情景/实际种子）——旧实现按裸根名去重会把
    H/M 与跨种子同索引的根压成一条，跨种子刷新甚至整批变 0。
    """

    current_keys = [_av_family_root_identity_key(row)
                    for row in (epoch or {}).get("roots", ())]
    materialized = set(registry.get("roots") or ())
    batch: List[Dict[str, Any]] = []
    unmaterialized: List[Dict[str, Any]] = []
    seen = set()
    for decl in declarations.get("declared") or ():
        key = _av_family_root_identity_key(decl)
        if key not in materialized:
            unmaterialized.append(dict(decl))
            continue
        if key in current_keys or key in seen:
            continue
        seen.add(key)
        batch.append({"root_id": decl["root_id"], "opponent_mix": decl["opponent_mix"],
                      "sub_scenario": decl["sub_scenario"],
                      "panel_seed": decl.get("panel_seed"),
                      "root_index": decl.get("root_index"),
                      "root_seed": decl.get("root_seed"),
                      "generator": decl.get("generator"),
                      "root_identity_schema": decl.get("root_identity_schema")})
    return batch, unmaterialized


def _av_commit_family(state: Dict[str, Any], run_root: Path, *,
                      attempt_refresh: bool,
                      budget: Optional[float] = None) -> Dict[str, Any]:
    """家族通道提交/挑战（与 normal 通道**同一套事务语义**；A2/P7b 逐条对齐）。

    事务基准 = 原家族席位 + 家族根集 + 家族 epoch（同一运行链继承）；换席与换
    epoch 只由 archive_mod.apply_challenge 的 committed 分支决定；任一非提交结局
    （声明未物化 / 部分完成 / 刷新批不合规 / 预算不足 / 无望入席）一律**保原席、
    保原家族 epoch**，新候选只留候选池与探索队列。
    """

    channel = _av_family_declared_channel(state)
    if channel is None:
        return {"status": "inactive"}
    allowed, scope = av_family_scope_allows(channel)
    if not allowed:
        # S4：未启用家族**不提交、不建 epoch、不改席位**（与"保原席原 epoch"同向，
        # 但停因单独具名，便于报告区分"跳过"与"挑战失败"）。
        state["family_scope"] = scope
        return {"status": "skipped_inactive_family", "channel": channel,
                "stop_reason": AV_FAMILY_INACTIVE_STOP_REASON,
                "refresh_status": AV_FAMILY_INACTIVE_STOP_REASON, "scope": scope,
                "missing": {}, "epoch_kept": None, "samples_or_epoch_produced": False,
                "note": ("S4：家族 {0} 在本版显式 inactive；不进入提交路径（不改席位、"
                         "不建 epoch）").format(channel)}
    archive_mod = av_archive()
    run_root = Path(run_root)
    archive_dir = run_root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / "av-archive.json"
    epochs_path = archive_dir / "family-epochs.json"
    commit_dir = archive_dir / "family-commit" / channel
    iter_dir = Path(state["iter_dir"])
    candidate_id = str(state["identity"]["candidate_id"])
    previous = _av_previous_archive(state, run_root)
    epochs, prov = _av_family_inherited_epochs(state, run_root)
    epoch = epochs.get(channel)
    recorded = _av_record_family_roots(run_root, state)
    channel_roots = list((recorded["channels"].get(channel) or {}).get("roots") or [])
    entries = _av_archive_entries_with(state, previous)
    pool_view = archive_mod.update_archive(entries)
    baseline = _av_baseline_archive(state, run_root, prefer_dir=prov.get("dir"))
    baseline_seats = _av_baseline_slots(baseline, pool_view)
    seats_before = list(baseline_seats.get(channel, ()))
    current_epoch_ids = [row["root_id"] for row in (epoch or {}).get("roots", ())]
    # A4/§13 A：挑战基准只带挑战通道的原席；探索席在提交点相对提交后的在案席位重算。
    challenge_base = dict(pool_view)
    challenge_base["slots"] = _av_frozen_seats(baseline_seats)

    def _tx(payload: Dict[str, Any]) -> Path:
        record = {"schema": "sitin-av-tx-family-refresh/1", "channel": channel,
                  "run_id": state.get("run_id"),
                  "iteration_no": state.get("iteration_no"),
                  "candidate_id": candidate_id, "epoch_source": prov,
                  "seats_before": seats_before}
        record.update(payload)
        return _av_tx_write(iter_dir, "family_refresh", record)

    def _kept_write(status: str, note: str, *, phase: Any = None,
                    missing: Any = None,
                    extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """非提交结局：保原家族席与原家族 epoch，只落候选池证据与事务件。

        A4/§13 A：冻结面只覆盖需要同根挑战的通道（本通道家族席 + 正常/其它家族
        通道）；探索席相对**提交后的在案席位**重算（排除在案 overall 与四家族席
        持有者 + 同行为去重），随本次档案事务一并提交。
        """

        kept = dict(previous) if previous else {}
        kept.setdefault("schema", archive_mod.ARCHIVE_SCHEMA)
        kept["entries"] = pool_view["entries"]
        seats = {key: list(ids or []) for key, ids in baseline_seats.items()}
        if not any(seats.values()):
            seats = {key: list(ids or [])
                     for key, ids in pool_view["slots"].items()}
        _av_commit_slots(kept, seats)
        queue = [cid for cid in (baseline.get("exploration_queue") or [])
                 if isinstance(cid, str)]
        for cid in ((extra or {}).get("exploration_queue") or []):
            if isinstance(cid, str) and cid not in queue:
                queue.append(cid)
        if candidate_id in kept["entries"] and candidate_id not in queue:
            queue.append(candidate_id)
        kept["exploration_queue"] = queue
        kept["family_challenge"] = {
            "channel": channel, "status": status, "phase": phase,
            "seats_kept": True, "epoch_kept": (epoch or {}).get("epoch"), "note": note}
        av_atomic_write_json(archive_path, kept)
        if epoch is not None:
            _av_write_family_epochs(epochs_path, epochs)
        refresh = {"channel": channel, "status": status, "note": note,
                   "phase": phase, "missing": missing, "seats_kept": True,
                   "epoch_kept": (epoch or {}).get("epoch"),
                   "seats_after": list(kept["slots"].get(channel, ())),
                   # A4：探索席不在冻结面内，如实报出本次提交后的探索席。
                   "exploration_after": list(kept["slots"].get("exploration", ()))}
        for key in ("budget", "needed", "exploration_queue", "challenger_value",
                    "incumbent_values"):
            if isinstance(extra, Mapping) and key in extra:
                refresh[key] = extra[key]
        _tx({"old_epoch": {"epoch_no": (epoch or {}).get("epoch"),
                           "roots": current_epoch_ids},
             "outcome": status, "phase": phase, "missing": missing, "note": note,
             "seats_after": refresh["seats_after"],
             "exploration_after": refresh["exploration_after"]})
        return {"status": "kept", "channel": channel, "phase": phase,
                "missing": missing, "refresh": refresh, "archive": kept}

    def _identity_blockers(channels_payload: Mapping[str, Any],
                           provenance: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """本通道的身份级阻塞项：登记表拒绝的历史根 + epoch 表的身份问题。"""

        return ([item for item in (channels_payload.get("refused") or ())
                 if item.get("channel") == channel]
                + [item for item in (provenance.get("identity_problems") or ())
                   if item.get("channel") in (None, channel)])

    if epoch is None:
        want = {"{0}_open".format(channel), "{0}_cost".format(channel)}
        sides = {str(row.get("sub_scenario")) for row in channel_roots}
        mixes = {str(row.get("opponent_mix")) for row in channel_roots}
        # —— A1 修复：无家族 epoch 时**先校验并解析已声明的核心格**，再决定结局 ——
        # 复审反例：旧实现直接返回 epoch_incomplete，已声明的 family_refresh 解析
        # 次数恒为 0 → 补根永不触发 → 首个家族通道（与首个家族席）不可达。
        declarations = _av_family_declarations(state, channel)
        registry = _av_family_root_registry(recorded["channels"])
        blocked = (list(declarations["problems"]) + list(registry["conflicts"])
                   + list(recorded.get("conflicts") or ())
                   + _identity_blockers(registry, prov))
        # ① 冲突声明 / 历史身份**先处理**：声明自相矛盾或台账里混着旧根身份时，
        #    既不能宣布建立完成，也不能靠"补齐评价"绕过（A1 复审：成功分支早于
        #    未物化/冲突分支是旧缺陷的一半）。
        if blocked:
            kept = _kept_write(
                "identity_conflict",
                ("家族通道无在案 epoch：存在冲突声明/历史身份 {0} 项，先处理再建立"
                 "（不建立 epoch、不调度补根）").format(len(blocked)),
                phase="declaration_conflict", extra={"blocked": blocked})
            kept.update({"status": "conflict", "phase": "declaration_conflict",
                         "blocked": blocked})
            return kept
        matrix = _av_family_core_matrix(channel, registry)
        if matrix["complete"]:
            # P1：核心格齐备即**先冻结清单**（此后只读），epoch 与需求集合同源。
            # P16-C5：清单不可用（不可读/不合法/身份不符/写不进去）⇒ 具名停止，
            # 保留原件、不建立 epoch、不按当前推导重定需求集合。
            try:
                av_family_core_root_list(
                    channel=channel, registry=registry,
                    freeze_path=archive_dir / "family-core-roots.json",
                    # epoch 的核心根声明一起参与需求集合推导（登记表可能还没物化齐）。
                    epoch_rows=list((epoch or {}).get("roots") or ()))
            except FamilyCoreListRefused as error:
                kept.update({
                    "status": "core_list_invalid", "phase": "core_list_invalid",
                    "stop_reason": error.stop_reason, "path": error.path,
                    "problems": list(error.problems),
                    "note": ("冻结核心根清单不可用：具名停止（保留原件；运行中不得"
                             "自动重定需求集合，也不得建立 epoch）")})
                state["stop_reason"] = error.stop_reason
                return kept
        core = [dict(root, sub_scenario=cell["sub_scenario"],
                     opponent_mix=cell["opponent_mix"])
                for cell in matrix["cells"].values()
                for root in ({"root_id": root_id} for root_id in
                             cell["roots"][:AV_FAMILY_CORE_ROOTS_PER_CELL])]
        _batch, unmaterialized = _av_family_refresh_batch(channel, declarations,
                                                          registry, epoch or {})
        if not unmaterialized and matrix["complete"]:
            # ② 逐格配额已齐 → 再验"入席候选对**全部核心根**都有合格评价"：
            #    缺格保持 pending（把缺的核心根交给补根层），不提交面板版本与席位。
            seats_now = [str(cid) for cid in (pool_view["slots"].get(channel) or ())]
            targets = seats_now or [candidate_id]
            gaps = {cid: _av_family_core_evidence_gaps(
                (pool_view.get("entries") or {}).get(cid), core)
                for cid in targets}
            gaps = {cid: items for cid, items in gaps.items() if items}
            if gaps:
                missing = {cid: ["{0}|{1}|{2}".format(item["sub_scenario"],
                                                     item["opponent_mix"],
                                                     item["root_id"])
                                 for item in items]
                           for cid, items in sorted(gaps.items())}
                kept = _kept_write(
                    "pending_core_evidence",
                    ("核心根已齐备，但入席候选尚未对全部核心根取得合格评价："
                     "先补这些根的条件评价，再建立首席（A1）"),
                    phase="epoch_core_fill", missing=missing,
                    extra={"core_gaps": gaps})
                kept.update({"status": "pending", "phase": "epoch_core_fill",
                             "missing": missing, "core_gaps": gaps,
                             "blocked": blocked})
                return kept
        if (not unmaterialized and matrix["complete"]
                and [str(cid) for cid in (pool_view["slots"].get(channel) or ())]):
            epoch_new = archive_mod.build_channel_epoch(channel, core)
            epochs[channel] = epoch_new
            _av_write_family_epochs(epochs_path, epochs)
            archive_new = dict(previous) if previous else {}
            archive_new.setdefault("schema", archive_mod.ARCHIVE_SCHEMA)
            archive_new["entries"] = pool_view["entries"]
            seats = {key: list(ids or []) for key, ids in baseline_seats.items()}
            if not any(seats.values()):
                seats = {key: list(ids or [])
                         for key, ids in pool_view["slots"].items()}
            else:
                seats[channel] = list(pool_view["slots"].get(channel, []))
            # A4/§13 A：家族通道换的是本通道席位；探索席相对换席后的在案席位重算。
            archive_new["slots"] = seats
            _av_commit_slots(archive_new, seats)
            archive_new["family_challenge"] = {
                "channel": channel, "status": "epoch_established",
                "seats_kept": False, "epoch_kept": None,
                "note": ("家族通道无在案 epoch：本迭代按家族根台账建立 epoch 1 并"
                         "初始化家族席（无在案席位可比）")}
            av_atomic_write_json(archive_path, archive_new)
            _tx({"old_epoch": None, "outcome": "epoch_established",
                 "new_epoch": epoch_new["epoch"],
                 "seats_after": list(seats.get(channel, ()))})
            return {"status": "established", "channel": channel, "epoch": epoch_new,
                    "archive": archive_new,
                    "refresh": {"channel": channel, "status": "epoch_established",
                                "seats_kept": False, "epoch": epoch_new["epoch"],
                                "roots": len(core)}}
        if unmaterialized:
            # 声明已给出但尚未物化：交给补根层**先执行这些核心格**（每个声明一次
            # 单根条件评价），补齐后重试提交 → 建立 epoch 1 与首个家族席。
            kept = _kept_write(
                "pending_declaration",
                ("家族通道无在案 epoch：先按**已声明的核心格**补齐条件评价，"
                 "两侧 × H/M 齐备后再建立首席（A1）"),
                phase="epoch_core_fill",
                extra={"unmaterialized": unmaterialized})
            kept.update({"status": "pending", "phase": "epoch_core_fill",
                         "unmaterialized": unmaterialized, "blocked": blocked})
            return kept
        seat_candidates = [str(cid) for cid in (pool_view["slots"].get(channel) or ())]
        gap = ("family_channel_epoch_incomplete:{0}:sides={1}:mixes={2}"
               ":declared={3}:unmaterialized=0:core_cells={4}:core_roots={5}"
               ":seat_candidates={6}".format(
                   channel, sorted(sides), sorted(mixes),
                   len(declarations["declared"]),
                   {key: cell["n_roots"] for key, cell in sorted(matrix["cells"].items())},
                   matrix["n_roots"], sorted(seat_candidates)))
        state.setdefault("input_gaps", []).append(gap)
        kept = _kept_write(
            "epoch_incomplete", gap,
            extra={"core_matrix": matrix, "seat_candidates": sorted(seat_candidates)})
        kept.update({"status": "epoch_incomplete", "reason": gap,
                     "core_matrix": matrix, "blocked": blocked})
        return kept

    if not attempt_refresh:
        return _kept_write("no_refresh_requested",
                           "调用方未请求家族刷新：保持原家族 epoch 与原家族席")

    declarations = _av_family_declarations(state, channel)
    registry = _av_family_root_registry(recorded["channels"])
    batch, unmaterialized = _av_family_refresh_batch(channel, declarations, registry,
                                                     epoch)
    blocked = (list(declarations["problems"]) + list(registry["conflicts"])
               + list(recorded.get("conflicts") or ())
               + _identity_blockers(registry, prov))
    if blocked:
        # A1/A2：声明冲突或历史身份混排时**不得**继续挑战/换 epoch：先把身份
        # 处理干净（旧目录以新身份重开），否则同根比较会拿两个不同的根相比。
        kept = _kept_write(
            "identity_conflict",
            "家族刷新批存在冲突声明/历史身份 {0} 项：先处理再复核".format(len(blocked)),
            phase="declaration_conflict", extra={"blocked": blocked})
        kept.update({"status": "conflict", "phase": "declaration_conflict",
                     "blocked": blocked})
        return kept
    def _reevaluation_pending() -> Dict[str, Any]:
        """P15：重评声明是**比较义务**——义务未完成时该通道必须保持 **pending**。

        缺陷路径（run6 实测）：9 条重评声明全部见证 ⇒ 刷新批为空 ⇒ 结局被分类成
        batch_invalid（kept）⇒ 迭代不进 REFRESH_PENDING ⇒ 补根步一轮都不跑。
        修法只改**结局分类**（kept → pending），不改原子提交语义：仍由 _kept_write
        保留原家族席与原家族 epoch、结果暂存，且**不把未评价记成已完成**。
        """

        recorded_now = _av_record_family_roots(run_root, state)
        registry_now = _av_family_root_registry(recorded_now["channels"])
        obligations = av_family_reevaluation_obligations(
            state=state, run_root=run_root, registry=registry_now, channel=channel,
            products=_av_family_evaluation_products(run_root),
            entries=dict((_av_previous_archive(state, run_root).get("entries")) or {}))
        tokens: Dict[str, List[str]] = {}
        for item in obligations["obligations"]:
            tokens.setdefault(str(item["candidate_id"]), []).append(str(item["token"]))
        return {"obligations": obligations,
                "missing": {cid: sorted(set(values)) for cid, values in tokens.items()}}

    pending_reevaluation = _reevaluation_pending()
    if pending_reevaluation["missing"]:
        # 有义务要补 ⇒ 结局是 pending（进补根步），而不是"刷新批不合规"。
        kept = _kept_write(
            "pending", ("家族重评声明（比较义务）尚未评价：本通道保持 pending，"
                        "交补根步为该候选补齐缺失的共同根边后重试提交"),
            phase="reevaluation", missing=pending_reevaluation["missing"],
            extra={"reevaluation": pending_reevaluation["obligations"]})
        kept.update({"status": "pending", "phase": "reevaluation",
                     "missing": pending_reevaluation["missing"],
                     "reevaluation": pending_reevaluation["obligations"]})
        return kept
    if unmaterialized:
        kept = _kept_write("pending_declaration",
                           "家族刷新批声明尚未物化：先按显式根声明评价再复核",
                           phase="declaration",
                           extra={"unmaterialized": unmaterialized})
        kept.update({"status": "pending", "phase": "declaration",
                     "missing": {}, "unmaterialized": unmaterialized,
                     "blocked": blocked})
        return kept
    verdict = archive_mod.family_refresh_batch_verdict(channel, batch)
    if not verdict["ok"]:
        kept = _kept_write("batch_invalid",
                           "家族刷新批复核未通过：{0}".format(verdict["reason"]),
                           extra={"batch": verdict, "batch_roots": batch})
        kept.update({"status": "kept", "blocked": blocked})
        return kept
    try:
        outcome: Mapping[str, Any] = archive_mod.apply_challenge(
            challenge_base, epoch, candidate_id, evaluations={candidate_id: {}},
            refresh_roots=batch, budget=budget, persist_dir=commit_dir)
    except ValueError as error:
        outcome = {"status": "refresh_rejected", "note": str(error)}
    if not isinstance(outcome, Mapping):
        outcome = {"status": "refresh_rejected", "note": "挑战返回非映射结果"}
    status = str(outcome.get("status") or "refresh_rejected")
    if status == "pending_partial":
        kept = _kept_write("pending_partial",
                           "家族挑战未补齐（{0}）：保原席原家族 epoch".format(
                               outcome.get("phase")),
                           phase=outcome.get("phase"),
                           missing=outcome.get("missing"),
                           extra={"batch_roots": batch})
        kept.update({"status": "pending", "phase": outcome.get("phase"),
                     "missing": outcome.get("missing"), "blocked": blocked})
        return kept
    if status != "committed":
        kept = _kept_write(status, str(outcome.get("note") or ""),
                           phase=outcome.get("phase"),
                           missing=outcome.get("missing"), extra=outcome)
        kept.update({"status": "kept", "blocked": blocked,
                     "batch_roots": batch})
        return kept

    new_epoch = outcome["new_epoch"]
    epochs[channel] = new_epoch
    _av_write_family_epochs(epochs_path, epochs)
    archive_new = dict(outcome["archive"])
    # A4/§13 A：家族席提交后**重算**探索席——挑战可能已经换了本家族席，排除集与
    # 去重参考必须取提交后的在案席位（同源漏洞，与正常通道同一处理）。
    _av_commit_slots(archive_new, _av_frozen_seats(archive_new.get("slots") or {}))
    archive_new["family_challenge"] = {
        "channel": channel, "status": "committed", "seats_kept": False,
        "epoch_before": outcome.get("epoch_before"),
        "epoch_after": new_epoch.get("epoch"),
        "participants": [row["candidate_id"] for row in outcome.get("ranking") or []],
        "note": ("全员在旧根 + 刷新根齐备 → 原子提交新家族 epoch 并用新根集统一"
                 "重排家族席")}
    av_atomic_write_json(archive_path, archive_new)
    _tx({"old_epoch": {"epoch_no": epoch.get("epoch"), "roots": current_epoch_ids},
         "outcome": "committed", "new_epoch": new_epoch.get("epoch"),
         "participants": archive_new["family_challenge"]["participants"],
         "refresh_roots": [row["root_id"] for row in batch],
         "ranking": outcome.get("ranking"), "persisted": outcome.get("persisted"),
         "seats_after": list(archive_new["slots"].get(channel, ())),
         "exploration_after": list(
             archive_new["slots"].get("exploration", ()))})
    refresh = dict(outcome, status="committed", channel=channel,
                   exploration_after=list(
                       archive_new["slots"].get("exploration", ())))
    return {"status": "committed", "channel": channel,
            "epoch_after": new_epoch.get("epoch"),
            "seats_after": list(archive_new["slots"].get(channel, ())),
            "archive": archive_new, "refresh": refresh}


def _av_family_step_prefix(candidate_id: Any, sub_scenario: Any, token: Any) -> str:
    """家族条件评价的账步前缀（含**选择集记号**：不同选择集是不同任务身份）。"""

    return "evaluate:{0}:{1}:{2}".format(str(candidate_id)[:12], str(sub_scenario),
                                         str(token))


def _av_family_expected_instances(item: Mapping[str, Any],
                                  tables_per_group: int) -> List[Dict[str, Any]]:
    """家族条件评价实例清单（根 × 臂 × 赛程）——真实副作用**之前**即可落盘。"""

    schedule = "conditional_stage:{0}_tables".format(int(tables_per_group))
    rows: List[Dict[str, Any]] = []
    indexes = [int(value) for value in (item.get("root_indexes") or ())]
    for position, root_id in enumerate(item["root_ids"]):
        index = (indexes[position] if position < len(indexes)
                 else _av_family_root_index_of(root_id))
        # 承载 S1 残留 ④：家族根种子进实例身份键（同候选同情景不同种子 → 键不同）。
        root_seed = item.get("root_seed")
        if root_seed is None and index is not None:
            root_seed = int(_av_family_item_descriptor(item,
                                                       root_index=index)["root_seed"])
        for arm in AV_INSTANCE_ARMS:
            rows.append(av_instance_row(
                candidate_id=item["candidate_id"],
                opponent_mix=item["opponent_mix"], panel_seed=item["panel_seed"],
                source_root_id=root_id, root_index=index,
                root_seed=(None if root_seed is None else int(root_seed)),
                seat=0, arm=arm, schedule=schedule,
                participant_id=item["candidate_id"],
                planned_tables=int(tables_per_group)))
    return rows


def _av_family_result_matches(evaluation: Mapping[str, Any], *,
                              item: Mapping[str, Any],
                              source: Mapping[str, Any]) -> Tuple[bool, str]:
    """家族条件评价结果对账：确实是**本身份 × 本子场景 × 本情景 × 本根**的产物。"""

    if not isinstance(evaluation, Mapping):
        return False, "结果不是映射"
    identity = evaluation.get("identity") or {}
    panel = evaluation.get("panel") or {}
    if str(panel.get("predicate")) != str(item["sub_scenario"]):
        return False, "子场景不符"
    if int(panel.get("panel_seed") or -1) != int(item["panel_seed"]):
        return False, "面板种子不符"
    if str(identity.get("opponent_mix")) != str(item["opponent_mix"]):
        return False, "对手情景不符"
    if str(identity.get("candidate_id")) != str(item["candidate_id"]):
        return False, "候选身份不符（不采用他者结果）"
    produced = {str(sample.get("source_root_id"))
                for sample in (evaluation.get("samples") or [])}
    wanted = {str(root_id) for root_id in item["root_ids"]}
    if produced != wanted:
        return False, "根清单不符（多 {0} / 缺 {1}）".format(
            sorted(produced - wanted), sorted(wanted - produced))
    if isinstance(evaluation.get("root_selection"), Mapping):
        # A2：带根选择标记的结果必须能核对**内容摘要**——跑的是不是被冻结的那个根，
        # 要在采用之前逐字对上（"跑完再丢弃"的结果不该能走到这里）。
        checked, why = _av_family_root_digests_match(evaluation, item=item)
        if not checked:
            return False, why
    return True, ""


def _av_family_root_digests_match(evaluation: Mapping[str, Any], *,
                                  item: Mapping[str, Any]) -> Tuple[bool, str]:
    """根内容摘要对账（A2）：逐样本比对本根**要求摘要**（由冻结参数重算）。

    替身执行器（P7c 的 FamilyEvalStub 等）不声明 root_selection 标记时走不到这里；
    真实执行器（_av_family_execute_evaluation → run_av_evaluation 的单根面板）必然
    带标记，因此"跑的是目标任务根"在真实路径上恒被核对。
    """

    selection = evaluation.get("root_selection") or {}
    indexes = [int(value) for value in (selection.get("indexes") or ())]
    if len(indexes) != len(item["root_ids"]):
        return False, "根选择长度与冻结根清单不符（{0} != {1}）".format(
            indexes, list(item["root_ids"]))
    for sample in evaluation.get("samples") or []:
        root_id = str(sample.get("source_root_id"))
        position = [str(value) for value in item["root_ids"]].index(root_id) \
            if root_id in [str(value) for value in item["root_ids"]] else None
        if position is None:
            return False, "样本根身份 {0} 不在冻结根清单内".format(root_id)
        index = indexes[position]
        if index != int(item["root_indexes"][position]):
            return False, "根序号不符（结果 {0} != 冻结 {1}）：不是目标任务根".format(
                index, item["root_indexes"][position])
        expected = av_family_root_requirement_digest(
            prefix_source=str(item.get("prefix_source") or "scripted_fixture"),
            predicate=str(item["sub_scenario"]), opponent_mix=str(item["opponent_mix"]),
            panel_seed=int(item["panel_seed"]), root_index=index)
        declared = str(sample.get("root_requirement_digest") or "")
        if not declared:
            return False, ("结果缺根要求摘要（root_requirement_digest）：无法证明跑的"
                           "就是冻结的根，不采用")
        if declared != expected:
            return False, "根要求摘要不符（结果 {0} != 冻结 {1}）".format(
                declared[:16], expected[:16])
        if not str(sample.get("root_content_digest") or ""):
            return False, "结果缺根内容摘要（root_content_digest）：不采用"
    return True, ""


def _av_family_execute_evaluation(*, state: Dict[str, Any], run_root: Path,
                                  ledger: "ActionValueLedger",
                                  authorization: Optional[Mapping[str, Any]],
                                  item: Mapping[str, Any],
                                  source: Mapping[str, Any],
                                  test_runtime_factory: Optional[
                                      Callable[[], Mapping[str, Any]]] = None
                                  ) -> Dict[str, Any]:
    """执行器（**唯一**真实家族条件评价调用点）：复用 run_av_evaluation。

    与条件步同一条通路：同一批次 7 授权门、同一共享账本（先预留后执行）、同一
    身份投影、同一结果准入；v2_behavior 路由的运行时在**组合处显式装配**（测试
    替身只能经 test_runtime_factory 显式注入，缺省即真实组合根运行时）。
    """

    opportunities = av_opportunities()
    plan = state.get("plan") or {}
    prefix_source = str(plan.get("prefix_source") or "scripted_fixture")
    # A2：根选择在**一切副作用之前**解出并校验（越界/缺种子即拒绝，零桌零产物）。
    indexes = [int(value) for value in (item.get("root_indexes") or ())]
    if len(indexes) != len(item["root_ids"]):
        return {"ok": False, "evaluation": None, "tables_executed": 0,
                "reason": "家族根选择与根清单长度不符（{0} != {1}）：不猜目标任务".format(
                    indexes, list(item["root_ids"]))}
    try:
        selection = av_conditional_root_selection(indexes)
    except ValueError as error:
        return {"ok": False, "evaluation": None, "tables_executed": 0,
                "reason": "家族根选择非法（早于一切执行）：{0}".format(error)}
    root_index = int(selection[0])
    # A3：身份与执行种子都来自**唯一描述符**；登记的真实执行种子必须与它逐字相等
    # （同一根 = 同一座牌山），不等价一律在启动任何桌赛之前拒绝。
    descriptor = _av_family_item_descriptor(item, root_index=root_index)
    root_seed = item.get("root_seed")
    if root_seed is None:
        root_seed = int(descriptor["root_seed"])
    elif int(root_seed) != int(descriptor["root_seed"]):
        return {"ok": False, "evaluation": None, "tables_executed": 0,
                "reason": ("补根种子与根身份不一致（{0} != {1}）：同一根不等价复现，"
                           "不启动任何桌赛").format(int(root_seed),
                                                    int(descriptor["root_seed"]))}
    expected_root_id = str(descriptor["root_id"])
    if [str(value) for value in item["root_ids"]] != [expected_root_id]:
        return {"ok": False, "evaluation": None, "tables_executed": 0,
                "reason": ("冻结根清单与根序号不等价（{0} != {1}）：不等价复现，"
                           "不启动任何桌赛").format(list(item["root_ids"]),
                                                     [expected_root_id])}
    runtime_kwargs: Dict[str, Any] = {}
    if prefix_source == "v2_behavior":
        try:
            runtime, assembly = _av_assemble_conditional_runtime(
                plan={"prefix_source": prefix_source,
                      "panel_seed": int(item["panel_seed"])},
                test_runtime_factory=test_runtime_factory)
        except opportunities.RuntimeAssemblyError as error:
            return {"ok": False, "evaluation": None, "tables_executed": 0,
                    "reason": "家族条件评价运行时装配失败（A1 fail-closed，不回退"
                              "替身/夹具）：{0}".format(error)}
        runtime_kwargs[("test_runtime" if assembly.get("explicit_test_entry")
                        else "runtime")] = runtime
    # 产物目录键含**选择集记号**（token，与 _av_family_run_evaluation 的检查点/
    # 结果目录同键 + execution 子目录）：同一（候选 × 子场景 × 情景）在不同根选择
    # 集上是不同任务身份，面板/评价产物不得互相覆盖（A2：跑 root005 与 root008
    # 是两次任务，不是一个任务的两次写）。
    out_dir = (Path(state["iter_dir"]) / "family"
               / "{0}-{1}-{2}-{3}".format(str(item["candidate_id"])[:12],
                                          item["sub_scenario"], item["opponent_mix"],
                                          item["token"]) / "execution")
    try:
        evaluation = run_av_evaluation(
            out_dir, str(source["source"]), predicate=str(item["sub_scenario"]),
            opponent=str(item["opponent_mix"]), ledger=ledger, admission=None,
            authorization=authorization, prefix_source=prefix_source,
            attempts_cap=8, panel_seed=int(item["panel_seed"]),
            step_token=str(item["token"]),
            # A2：把**冻结的根选择 + 根种子**贯穿到前缀执行器（单根面板只跑它）。
            root_indexes=[root_index], root_seed=int(root_seed), **runtime_kwargs)
    except AV_LEDGER_FAILURE_ERRORS as error:
        # P8：`TaskAlreadySettled` 等账本异常同样转成失败返回（补根失败保原席原
        # epoch），不抛穿 worker（run2 的抛穿点就在这里）。
        return {"ok": False, "evaluation": None, "tables_executed": 0,
                "reason": "家族条件评价账本拒绝（记账/预算，{0}）：{1}".format(
                    type(error).__name__, error)}
    except SystemExit as error:
        return {"ok": False, "evaluation": None, "tables_executed": 0,
                "reason": "家族条件评价授权缺口：{0}".format(error)}
    # 身份投影统一（与自然面板/补根同源）：面板按直接计算 id 报身份，编排用绑定 id。
    for sample in evaluation.get("samples") or []:
        sample["panel_reported_candidate_id"] = sample.get("candidate_id")
        sample["candidate_id"] = str(item["candidate_id"])
        for arm in (sample.get("arms") or {}).values():
            if arm.get("candidate_id") not in (None, AV_BASELINE_ID):
                arm["candidate_id"] = str(item["candidate_id"])
    tables_executed = int((evaluation.get("panel") or {}).get(
        "tables_full_executed") or 0)
    # A2：内容摘要校验（采用结果之前）——要求摘要必须等于由**冻结声明**重算的值，
    # 内容摘要必须非空；不符即整份结果不采用（不把"跑了别的根"的结果当本任务结果）。
    matched, why = _av_family_root_digests_match(evaluation, item=item)
    if not matched:
        return {"ok": False, "evaluation": evaluation,
                "tables_executed": tables_executed,
                "reason": "家族条件评价根摘要校验未过：{0}（不采用）".format(why)}
    matched, why = _av_family_result_matches(evaluation, item=item, source=source)
    if not matched:
        return {"ok": False, "evaluation": evaluation,
                "tables_executed": tables_executed,
                "reason": "家族条件评价结果不符：{0}（不采用）".format(why)}
    return {"ok": True, "evaluation": evaluation,
            "tables_executed": tables_executed, "reason": ""}


#: 一次家族条件评价在账本上的**三个账户**（与 _step_conditional 同族口径）：
#: 前缀生成 1 次、被启动的真实桌赛实例（部分桌）、双臂完整阶段桌赛。
AV_FAMILY_EVAL_ACCOUNTS: Tuple[str, ...] = ("prefix_generation", "tables_partial",
                                            "tables_full")


def _av_family_partial_charged(evaluation: Mapping[str, Any]) -> Optional[float]:
    """本次家族评价的 tables_partial **实计费额**（结果可用时按实结算）。

    取值面：评价自身的 `tables_partial_charged`（run_av_evaluation 的产物面板块；
    兼容旧产物里嵌在 panel 下的写法）。**缺键即返回 None**——调用方退回"按预留额保守
    结算"，不按 0 静默吞掉已发生的费用。
    """

    for holder in (evaluation, evaluation.get("panel") or {}):
        if not isinstance(holder, Mapping):
            continue
        value = holder.get("tables_partial_charged")
        if value is None:
            continue
        if not (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)) and float(value) >= 0):
            return None
        return float(value)
    return None


def _av_family_reconcile_attempts(ledger: "ActionValueLedger", *, step_prefix: str,
                                  reason: str,
                                  executed: Optional[Mapping[str, Optional[float]]] = None
                                  ) -> Dict[str, Dict[str, Any]]:
    """家族条件评价的**逐账户**恢复对账（口径与 `_step_conditional` 一致）。

    R9/P8 缺陷：家族路径原先只对 `tables_full` 让位，`prefix_generation` /
    `tables_partial` 的旧已结算行仍在 ⇒ 第二轮重试同一根时重新预留同一 step_id 抛
    `TaskAlreadySettled`（关口二 run2 的生产侧崩溃）。

    - `executed=None`：结果不可用（未产出/被拒）⇒ 三个账户一律「在途保守结算 +
      已结算行让位给新尝试，费用保留」；
    - `executed={账户: 实执行数}`：结果在盘上、采用并结算 ⇒ 在途预留按**实执行数**结算
      （prefix_generation 恒 1.0；tables_partial 按本次评价的 `tables_partial_charged`；
      tables_full 按 `tables_full_executed`），已结算行**不动**（结果可用 ⇒ 不让位）。
      某账户实执行数缺失（None）⇒ 该账户退回保守结算（按预留额，不下调也不吞）。
    """

    report: Dict[str, Dict[str, Any]] = {}
    for account in AV_FAMILY_EVAL_ACCOUNTS:
        exact = None if executed is None else executed.get(account)
        report[account] = av_reconcile_ledger_attempts(
            ledger, step_prefix=step_prefix, account=account,
            result_available=executed is not None,
            executed=(None if exact is None else float(exact)),
            reason="{0}｜账户 {1}".format(reason, account))
    return report


def _av_family_ledger_failure(record: Dict[str, Any], error: BaseException, *,
                              where: str) -> Dict[str, Any]:
    """账本异常 → 家族评价的**失败返回**（不抛穿 worker；补根按设计保原席原 epoch）。"""

    reason = ("家族条件评价账本拒绝（{0}，{1}）：{2}（补根失败：保持原家族席与原"
              "epoch，挑战者留候选池）").format(where, type(error).__name__, error)
    record.update({"status": "failed", "reason": reason})
    return {"attempt": record, "evaluation": None, "reason": reason}


def _av_family_round_fact(item: Mapping[str, Any], *, round_no: int, attempted: bool,
                          evidence_added: bool = False, status: Optional[str] = None,
                          reason: Optional[str] = None,
                          roots_added: Sequence[str] = (),
                          n_samples: Optional[int] = None) -> Dict[str, Any]:
    """一轮内**单个工件**的可复算事实（无进展判定的唯一输入，逐轮落事务件）。"""

    root_id = str((item.get("root_ids") or [""])[0])
    return {
        "round": int(round_no),
        "root_key": _av_family_root_identity_key({"root_id": root_id}),
        "root_id": root_id, "root_seed": item.get("root_seed"),
        "sub_scenario": item.get("sub_scenario"),
        "opponent_mix": item.get("opponent_mix"), "panel_seed": item.get("panel_seed"),
        "root_index": ((item.get("root_indexes") or [None])[0]),
        "kind": item.get("kind"), "token": item.get("token"),
        "attempted": bool(attempted), "evidence_added": bool(evidence_added),
        "status": status, "reason": reason,
        "roots_added": sorted(str(value) for value in (roots_added or ())),
        "n_samples": n_samples,
    }


def _av_family_split_no_progress(items: Sequence[Mapping[str, Any]], *,
                                 registry: Mapping[str, Any], round_no: int,
                                 ) -> Tuple[List[Mapping[str, Any]], List[Dict[str, Any]]]:
    """按**无进展登记**把工作项分成「可执行」与「已停止」两组（R9/P8）。

    停止判据是可复算事实：该根的完整身份已连续 `AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS`
    轮被真实评价而**没有产出任何新证据**（无可用样本、也未新登记根）。停止只针对该根，
    同一轮的其余工件照常推进；停止的根**不再产生任何费用**。
    """

    runnable: List[Mapping[str, Any]] = []
    stopped: List[Dict[str, Any]] = []
    for item in items:
        key = _av_family_root_identity_key(
            {"root_id": str((item.get("root_ids") or [""])[0])})
        record = dict((registry or {}).get(key) or {})
        rounds = int(record.get("rounds") or 0)
        if rounds < AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS:
            runnable.append(item)
            continue
        stopped.append({
            "root_id": key, "root_seed": item.get("root_seed"),
            "sub_scenario": item.get("sub_scenario"),
            "opponent_mix": item.get("opponent_mix"),
            "panel_seed": item.get("panel_seed"),
            "root_index": ((item.get("root_indexes") or [None])[0]),
            "kind": item.get("kind"), "token": item.get("token"),
            "rounds": rounds, "first_round": record.get("first_round"),
            "last_round": record.get("last_round"),
            "last_reason": record.get("last_reason"),
            "stop_reason": "family_refill_no_progress",
            "note": ("该根已连续 {0} 轮被评价而无新证据（前缀未被见证/无可用样本）："
                     "停止重试该根，不再花费评价费用").format(rounds),
            "at_round": int(round_no)})
    return runnable, stopped


def _av_family_run_evaluation(state: Dict[str, Any], run_root: Path,
                              ledger: "ActionValueLedger",
                              authorization: Optional[Mapping[str, Any]],
                              item: Mapping[str, Any], source: Mapping[str, Any],
                              test_runtime_factory: Optional[
                                  Callable[[], Mapping[str, Any]]] = None
                              ) -> Dict[str, Any]:
    """执行/复用**一次**家族条件评价（检查点 → 盘上结果对账 → 新尝试）。

    事务顺序与自然面板补根（P7b）**同源**：先落实例"已开始" → 预留（由
    run_av_evaluation 经同一共享账本完成）→ 执行 → 结算 → 完成检查点；任何一步
    中断都可由下一次调用按同一顺序复原：不重跑、不重复计费。
    """

    iter_dir = Path(state["iter_dir"])
    candidate_id = str(item["candidate_id"])
    # A2：根选择在这里**再解一次**，且早于检查点/实例台账/费用预留——越界或与冻结
    # 根身份不等价一律返回失败：不写"已开始"、不建目录、不启动任何桌赛。
    raw_indexes = [int(value) for value in (item.get("root_indexes") or ())]
    try:
        selection = av_conditional_root_selection(raw_indexes)
    except ValueError as error:
        reason = "家族根选择非法（早于一切副作用）：{0}".format(error)
        return {"attempt": {"candidate_id": candidate_id, "status": "rejected",
                            "root_indexes": list(raw_indexes), "reason": reason},
                "evaluation": None, "reason": reason}
    expected_ids = [_av_family_item_descriptor(item, root_index=int(selection[0]))["root_id"]] \
        if selection else []
    if [str(value) for value in item["root_ids"]] != expected_ids:
        reason = ("家族根选择与冻结根清单不等价（{0} != {1}）：不等价复现，"
                  "不启动任何桌赛").format(list(item["root_ids"]), expected_ids)
        return {"attempt": {"candidate_id": candidate_id, "status": "rejected",
                            "root_indexes": list(raw_indexes), "reason": reason},
                "evaluation": None, "reason": reason}
    # 检查点/结果目录键带**选择集记号**（token）：同一（候选 × 子场景 × 情景）在
    # 不同根选择集上是不同任务身份——声明批物化与点名缺失根不得互相顶替结果。
    key = "{0}-{1}-{2}-{3}".format(candidate_id[:12], item["sub_scenario"],
                                   item["opponent_mix"], item["token"])
    panel_dir = iter_dir / "family" / key
    result_path = panel_dir / "evaluation.json"
    checkpoint_name = "family-" + key
    step_prefix = _av_family_step_prefix(candidate_id, item["sub_scenario"],
                                         item["token"])
    tables_per_group = int(_av_refresh_contract()["group"]["tables_per_group"])
    checkpoint = av_checkpoint_load(iter_dir, checkpoint_name)
    previous_attempt = int((checkpoint or {}).get("attempt_no") or 0)
    attempt_no = max(1, previous_attempt)
    rows = av_ledger_rows_for_step(ledger, step_prefix=step_prefix,
                                   account="tables_full")
    expected = _av_family_expected_instances(item, tables_per_group)
    record: Dict[str, Any] = {
        "candidate_id": candidate_id, "sub_scenario": item["sub_scenario"],
        "opponent_mix": item["opponent_mix"], "panel_seed": int(item["panel_seed"]),
        "root_ids": list(item["root_ids"]), "root_indexes": list(item["root_indexes"]),
        "root_seeds": [int(item["root_seed"])] if item.get("root_seed") is not None
        else [],
        "kind": item.get("kind"), "token": item.get("token"),
        "step_prefix": step_prefix, "planned_tables": float(item["planned_tables"]),
        "source": {"origin": source.get("origin"), "sha256": source.get("sha256")}}
    evaluation: Optional[Mapping[str, Any]] = None
    reuse: Optional[str] = None
    if av_checkpoint_result_matches(checkpoint, result_path):
        evaluation = json.loads(result_path.read_text(encoding="utf-8"))
        reuse = "checkpoint"
    elif result_path.is_file() and rows:
        adopted: Optional[Mapping[str, Any]] = None
        try:
            adopted = json.loads(result_path.read_text(encoding="utf-8"))
        except ValueError:
            adopted = None
        if isinstance(adopted, Mapping):
            matched, why = _av_family_result_matches(adopted, item=item, source=source)
            if matched:
                executed = int((adopted.get("panel") or {}).get(
                    "tables_full_executed") or 0)
                # P8：**逐账户**结算——prefix_generation 恒 1.0；tables_partial 按本次
                # 评价自身的 tables_partial_charged；tables_full 按 tables_full_executed。
                record["reconcile"] = _av_family_reconcile_attempts(
                    ledger, step_prefix=step_prefix,
                    executed={"prefix_generation": 1.0,
                              "tables_partial": _av_family_partial_charged(adopted),
                              "tables_full": float(executed)},
                    reason="家族条件评价 {0}（结果在盘上，采用并结算）".format(key))
                evaluation = adopted
                reuse = "reconciled_result_on_disk"
            else:
                record["reconcile_note"] = why
    if evaluation is None:
        attempt_no = previous_attempt + 1
        try:
            # P8：三个账户都要让位（结果不可用 ⇒ 结算/supersede，费用保留）。只让位
            # tables_full 会把 prefix_generation/tables_partial 的旧已结算行留下 ⇒
            # 随后 run_av_evaluation 重新预留同一 step_id 抛 TaskAlreadySettled。
            record["reconcile"] = _av_family_reconcile_attempts(
                ledger, step_prefix=step_prefix,
                reason="家族条件评价 {0}（旧尝试让位，失败成本保留）".format(key))
        except AV_LEDGER_FAILURE_ERRORS as error:
            return _av_family_ledger_failure(record, error, where="恢复对账")
        av_instances_apply(iter_dir,
                           updates=[dict(row, status="started") for row in expected],
                           attempt_no=attempt_no,
                           iteration_no=int(state.get("iteration_no") or 0),
                           run_id=str(state.get("run_id") or ""),
                           mirror_root=run_root)
        av_checkpoint_write(iter_dir, checkpoint_name, {
            "status": "started", "step": "REFRESH_PENDING",
            "candidate_id": candidate_id, "sub_scenario": item["sub_scenario"],
            "opponent_mix": item["opponent_mix"], "attempt_no": attempt_no,
            "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
            "step_prefix": step_prefix,
            "cost_planned": float(item["planned_tables"]), "cost_charged": None,
            "instance_keys": [row["instance_key"] for row in expected],
            "started_at_utc": utc_now()})
        try:
            result = _av_family_execute_evaluation(
                state=state, run_root=run_root, ledger=ledger,
                authorization=authorization, item=item, source=source,
                test_runtime_factory=test_runtime_factory)
        except AV_LEDGER_FAILURE_ERRORS as error:
            # 执行器自身已把账本异常转成 ok=False；这里是**兜底**（替身/未来调用点
            # 直接抛账本异常时同样不得抛穿 worker）。
            record.update({"status": "failed", "reason": str(error)})
            av_instances_apply(iter_dir,
                               updates=[dict(row, status="aborted",
                                             reason=str(error)) for row in expected],
                               attempt_no=attempt_no,
                               iteration_no=int(state.get("iteration_no") or 0),
                               run_id=str(state.get("run_id") or ""),
                               mirror_root=run_root)
            return _av_family_ledger_failure(record, error, where="执行")
        if not result.get("ok"):
            record.update({"status": "failed", "reason": result.get("reason")})
            av_instances_apply(iter_dir,
                               updates=[dict(row, status="aborted",
                                             reason=str(result.get("reason")))
                                        for row in expected],
                               attempt_no=attempt_no,
                               iteration_no=int(state.get("iteration_no") or 0),
                               run_id=str(state.get("run_id") or ""),
                               mirror_root=run_root)
            _av_refresh_abort(run_root, ledger, expected, step_prefix=step_prefix,
                              attempt_no=attempt_no,
                              reason=str(result.get("reason")),
                              iteration_no=int(state.get("iteration_no") or 0),
                              run_id=str(state.get("run_id") or ""),
                              iter_dir=iter_dir)
            return {"attempt": record, "evaluation": None,
                    "reason": record["reason"]}
        evaluation = result["evaluation"]
        record["tables_executed"] = result.get("tables_executed")
    if not isinstance(evaluation, Mapping):
        record.update({"status": "failed", "reason": "家族条件评价结果不是映射"})
        return {"attempt": record, "evaluation": None, "reason": record["reason"]}
    if not result_path.is_file():
        # 不可变结果落盘：实例台账的 result_digest 与检查点复用判据都必须指向
        # 一份**真实存在、可复算**的结果产物（不引用内存对象）。
        panel_dir.mkdir(parents=True, exist_ok=True)
        av_atomic_write_json(result_path, evaluation)
    executed = int((evaluation.get("panel") or {}).get("tables_full_executed") or 0)
    instance_report = av_instances_apply(
        iter_dir,
        updates=[dict(row, status="completed", tables=int(tables_per_group),
                      result_digest=_av_file_digest(result_path),
                      result_path=str(result_path)) for row in expected],
        attempt_no=attempt_no, iteration_no=int(state.get("iteration_no") or 0),
        run_id=str(state.get("run_id") or ""), mirror_root=run_root)
    av_checkpoint_write(iter_dir, checkpoint_name, {
        "status": "completed", "step": "REFRESH_PENDING",
        "candidate_id": candidate_id, "sub_scenario": item["sub_scenario"],
        "opponent_mix": item["opponent_mix"], "attempt_no": attempt_no,
        "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
        "step_prefix": step_prefix, "cost_planned": float(item["planned_tables"]),
        "cost_charged": executed, "result_path": str(result_path),
        "result_sha256": _av_file_digest(result_path),
        "root_ids": list(item["root_ids"]),
        "instance_keys": [row["instance_key"] for row in expected],
        "reused_from": reuse, "instances": instance_report,
        "completed_at_utc": utc_now()})
    record.update({"status": "completed", "reuse": reuse, "attempt_no": attempt_no,
                   "tables_executed": executed, "result_path": str(result_path)})
    return {"attempt": record, "evaluation": evaluation, "instances": instance_report}


def _av_family_merge_fills(state: Dict[str, Any], run_root: Path,
                           fills: Mapping[str, Any]) -> Dict[str, Any]:
    """把家族补根/声明评价的样本按**完整根身份增量合并**进对应身份条目（同一合并器）。

    只写 entries 的 family_evaluations——换席仍只由 apply_challenge 的 committed
    分支决定（提交条件不变，不混新旧均值）。
    """

    archive_mod = av_archive()
    archive_path = Path(run_root) / "archive" / "av-archive.json"
    archive = _av_previous_archive(state, run_root)
    entries = dict(archive.get("entries") or {})
    report: Dict[str, Any] = {}
    for candidate_id, payload in sorted(fills.items()):
        item, result = payload
        evaluation = result.get("evaluation") or {}
        samples = list(evaluation.get("samples") or [])
        selectable, excluded = _av_split_selectable(samples)
        base = {"candidate_id": candidate_id, "sub_scenario": item["sub_scenario"],
                "opponent_mix": item["opponent_mix"],
                "panel_seed": item["panel_seed"], "root_ids": list(item["root_ids"]),
                "n_samples": len(selectable), "n_excluded_non_selectable": len(excluded),
                "roots_added": []}
        if selectable:
            merged = archive_mod.merge_archive_entry(entries.get(candidate_id),
                                                     candidate_id, selectable,
                                                     safety="PASS")
            entries[candidate_id] = merged
            merge_block = merged.get("evidence_merge") or {}
            base["roots_added"] = sorted(merge_block.get("added") or [])
            base["cells_qualified"] = list(merge_block.get("cell_qualified") or [])
        report[candidate_id] = base
    archive["entries"] = entries
    av_atomic_write_json(archive_path, archive)
    return report


def _av_family_fill_items(*, state: Mapping[str, Any], outcome: Mapping[str, Any],
                          registry: Mapping[str, Any], channel: str,
                          missing_override: Optional[Mapping[str, Sequence[str]]] = None,
                          ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """家族补根/声明物化 → 可执行工作项（一次评价 = 一个已锁定的根身份）。

    P1：missing_override 给出**冻结核心根清单逐键推导**的缺失集合时以它为准
    （生产自报的 missing 只作对照；旧口径按"当时的行集合"推缺失，会少算核心根）。
    """

    items: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    candidate_id = str(state["identity"]["candidate_id"])

    prefix_source = str((state.get("plan") or {}).get("prefix_source")
                        or "scripted_fixture")

    def _item(cid: str, sub: str, mix: str, seed: Any, index: Any,
              kind: str, *, root_seed: Any = None,
              token: Any = None) -> Dict[str, Any]:
        """补根工作项：根身份与执行种子一律取自**唯一描述符**（A3）。

        显式给了 root_seed（登记表里记下的**真实执行种子**）就逐字沿用——补根跑的
        必须是同一座牌山；描述符负责核对身份，种子一致性由调用方在调度前比对。
        """
        descriptor = av_family_root_descriptor(
            prefix_source=prefix_source, sub_scenario=sub, opponent_mix=mix,
            panel_seed=seed, root_index=index)
        effective_seed = (int(root_seed) if root_seed is not None
                          else int(descriptor["root_seed"]))
        effective_token = (str(token) if token
                           else "{0}-s{1}-idx{2}".format(mix, int(seed), int(index)))
        return {"candidate_id": cid, "sub_scenario": sub, "opponent_mix": mix,
                "panel_seed": int(seed), "root_indexes": [int(index)],
                "root_seed": effective_seed,
                "root_ids": [str(descriptor["root_id"])], "seats_per_root": 1,
                "root_descriptor": descriptor,
                "planned_tables": AV_TABLES_PER_FAMILY_EVALUATION, "kind": kind,
                "token": effective_token,
                "prefix_source": prefix_source,
                "step_prefix": _av_family_step_prefix(cid, sub, effective_token)}

    for decl in outcome.get("unmaterialized") or ():
        try:
            # A2：根序号越界的工作项在**调度前**拦下（不启动任何桌赛）。
            index = av_family_root_index(int(decl["root_index"]))
        except (TypeError, ValueError) as error:
            blocked.append({"candidate_id": candidate_id,
                            "sub_scenario": decl.get("sub_scenario"),
                            "opponent_mix": decl.get("opponent_mix"),
                            "reason": "声明根序号非法（不调度）：{0}".format(error)})
            continue
        items.append(_item(candidate_id, str(decl["sub_scenario"]),
                           str(decl["opponent_mix"]), decl["panel_seed"],
                           index, "declaration"))
    missing_map: Mapping[str, Sequence[str]] = (
        missing_override if missing_override is not None
        else (outcome.get("missing") or {}))
    for cid in sorted(missing_map):
        for token in (missing_map.get(cid) or ()):
            parts = str(token).split("|")
            if len(parts) != 3:
                blocked.append({"candidate_id": cid, "token": token,
                                "reason": ("家族缺失令牌不可解析（应为"
                                           "子场景|情景|根身份）")})
                continue
            sub, mix, root_id = parts
            cell = (registry.get("cells") or {}).get(
                "{0}|{1}|{2}".format(sub, mix, root_id))
            if cell is None:
                refused = [item for item in (registry.get("refused") or ())
                           if str(item.get("root_id")) == root_id]
                problems_text = "; ".join(
                    problem for item in refused for problem in (item.get("problems") or ()))
                blocked.append({"candidate_id": cid, "token": token, "root_id": root_id,
                                "reason": (
                                    "根不可调度：{0}".format(problems_text)
                                    if refused else
                                    "根未登记复现参数（不猜 panel_seed/根序号）："
                                    "该根补根不可调度")})
                continue
            registration = av_family_root_seed_of_record(dict(cell))
            if (not registration.get("recovered")
                    or registration.get("root_seed") is None):
                blocked.append({"candidate_id": cid, "token": token, "root_id": root_id,
                                "reason": ("登记根的真实执行种子不可恢复：{0}"
                                           "（不静默赋新种子，补根停止）").format(
                                               "；".join(
                                                   registration.get("problems")
                                                   or ("未知原因",)))})
                continue
            if (cell.get("panel_seed") is None or cell.get("root_index") is None):
                blocked.append({"candidate_id": cid, "token": token, "root_id": root_id,
                                "reason": ("根未登记复现参数（不猜 panel_seed/根序号）："
                                           "该根补根不可调度")})
                continue
            try:
                index = av_family_root_index(int(cell["root_index"]))
            except (TypeError, ValueError) as error:
                blocked.append({"candidate_id": cid, "token": token,
                                "root_id": root_id,
                                "reason": "登记根序号非法（不调度）：{0}".format(error)})
                continue
            item = _item(cid, sub, mix, cell["panel_seed"], index, "missing_root",
                         root_seed=int(registration["root_seed"]), token=token)
            if item["root_ids"] != [root_id]:
                blocked.append({"candidate_id": cid, "token": token,
                                "root_id": root_id,
                                "reason": ("根身份与登记序号不一致（{0} != {1}）："
                                           "不等价复现，不采用").format(
                                               item["root_ids"][0], root_id)})
                continue
            if int(item["root_seed"]) != int(registration["root_seed"]):
                blocked.append({"candidate_id": cid, "token": token,
                                "root_id": root_id,
                                "reason": ("补根种子与登记的真实执行种子不一致（{0} != {1}）："
                                           "不等价复现，不采用").format(
                                               item["root_seed"],
                                               registration["root_seed"])})
                continue
            items.append(item)
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        key = (item["candidate_id"], item["sub_scenario"], item["opponent_mix"],
               item["token"])
        if key in seen:
            blocked.append(dict(item, reason="同一评价项重复点名（去重：不重复计费）"))
            continue
        seen.add(key)
        unique.append(item)
    return unique, blocked


# ===========================================================================
# P15 REEVAL-SCHED（2026-09-18，run6 实测）· 重评声明是「比较义务」，不是「刷新发现」
#
# 缺陷：计划按 G2 接口发出 9 条 intent=reevaluate_registered_root 声明（在席者 8 个核心
# 根逐字带冻结描述符 + 1 条指定旧根）。声明**全部见证**（unmaterialized 为空）⇒ 迭代不进
# pending；又因为没有新根声明 ⇒ 刷新批为空 ⇒ batch_invalid ⇒ 补根步一轮都不跑。
# 结果：声明被见证，却从来没有变成评价 ⇒ 挑战者的共同根边仍是 0/16（缺 8 根 / 32 桌）。
#
# 语义（裁定 §3 第 3 步 / §4，与设计「挑战者先补齐该通道当前全部根…部分身份时保持原
# epoch 原席、结果暂存 pending」一致）：
#   - **重评声明 = 比较义务**：只要某格有 intent=reevaluate_registered_root 且该根已登记、
#     见证可用，而目标候选在该根上还没有可核评价，补根步就**必须**为该根排评价；
#     不得因为「没有待发现的新根」而整批跳过；
#   - 逐格配额、预算门、身份面、原子提交语义**一律不放宽**：本轮照样走预算门与
#     「先预留后执行」，提交仍只在全部必需边齐备时发生；未评价**绝不**记成已完成，
#     也不写「epoch 已刷新」；
#   - 停因分三类且可分：**预算不足** / **见证不足（INSUFFICIENT）** / **无待评价重评声明**；
#     最后一类只在**确实没有任何重评声明**时出现（有声明却停在 batch_invalid/
#     unschedulable 这类「没有新根可发现」的表述上，正是本包要修的表达错误）。
# ===========================================================================

#: 重评义务账目 schema（进 state.family_fill.reevaluation 与事务件）。
AV_FAMILY_REEVALUATION_SCHEMA = "sitin-av-family-reevaluation/1"
#: 三类停因 + 两条解析/提交侧记号（**互不混用**）。
AV_FAMILY_REEVAL_NO_DECLARATION = "family_reevaluation_no_declaration"
AV_FAMILY_REEVAL_WITNESS_INSUFFICIENT = "family_reevaluation_witness_insufficient"
AV_FAMILY_REEVAL_BUDGET_INSUFFICIENT = "family_reevaluation_budget_insufficient"
AV_FAMILY_REEVAL_EDGES_PENDING = "family_reevaluation_edges_evaluated_old_seats_kept"
AV_FAMILY_REEVAL_EDGES_EVALUATED = "family_reevaluation_edges_evaluated_pending_commit"
AV_FAMILY_REEVAL_UNRESOLVED_ROOT = "family_reevaluation_root_unresolved"
#: 「指定旧根」的运行时解析来源（计划可写 resolve=<source>）：读**前序迭代的实跑结果**，
#: 不猜根序号（run6 的计划行 root_index=None + resolve=iteration_1_conditional_root）。
AV_FAMILY_REEVAL_RESOLVERS: Tuple[str, ...] = ("iteration_1_conditional_root",)


def _av_family_reevaluation_rows(state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """声明里的**重评行**（优先取解析结果，回退计划原文）；只认 intent=reevaluate。

    P11 的解析结果（state.family_refresh_resolved.resolved）已经带 witness 结论与逐字
    冻结描述符；没有解析结果时回退计划原文（旧状态/夹具路径的行为逐字不变）。
    """

    resolution = state.get("family_refresh_resolved") or {}
    source: Sequence[Any] = list(resolution.get("resolved") or ())
    if not source:
        source = list(((state.get("plan") or {}).get("family_refresh")) or ())
    rows: List[Dict[str, Any]] = []
    for row in source:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("intent") or "") != AV_FAMILY_REFRESH_INTENT_REEVALUATE:
            continue
        rows.append(dict(row))
    return rows


def av_family_reevaluation_resolve_root(state: Mapping[str, Any], run_root: Path,
                                       row: Mapping[str, Any]) -> Dict[str, Any]:
    """一行重评声明 → 冻结描述符（root_index / root_seed / root_id）。

    三条互斥结论（**不猜、不默认 0**）：

      - row 自带 int root_index → 直接用（连同 root_seed 逐字冻结）；
      - root_index 缺失且有 resolve 提示 → 按提示读**前序迭代的实跑结果**取该根
        （iteration_1_conditional_root = iterations/iter-01/conditional/evaluation.json
         的样本根序号与真实执行种子）；
      - 解析不出来 → resolved=False + 具名原因（调用方据此**具名拒绝**该行，
        绝不静默跳过、也绝不默认成 root000）。
    """

    plan = state.get("plan") or {}
    prefix_source = str(plan.get("prefix_source") or "scripted_fixture")
    sub = str(row.get("sub_scenario") or "")
    mix = str(row.get("opponent_mix") or "")
    panel_seed = row.get("panel_seed")
    raw_index = row.get("root_index")
    index: Optional[int] = None
    source = "declared"
    if isinstance(raw_index, int) and not isinstance(raw_index, bool):
        index = int(raw_index)
    else:
        hint = str(row.get("resolve") or "")
        if hint and hint not in AV_FAMILY_REEVAL_RESOLVERS:
            return {"resolved": False, "source": hint, "reason": (
                "resolve 提示 {0!r} 不在已登记解析器 {1} 内：不猜根序号".format(
                    hint, list(AV_FAMILY_REEVAL_RESOLVERS)))}
        if hint:
            evaluation_path = (Path(run_root) / "iterations" / "iter-01"
                               / "conditional" / "evaluation.json")
            payload = _load_json_file(evaluation_path)
            samples = list((payload or {}).get("samples") or ())
            match = [item for item in samples
                     if str(item.get("scenario") or "") == sub
                     and str(item.get("opponent_mix") or "") == mix]
            if not match:
                return {"resolved": False, "source": hint, "reason": (
                    "按 resolve={0} 读 {1} 取该根失败：没有（{2} × {3}）的样本——"
                    "指定旧根无法解析，具名拒绝（不猜根序号）".format(
                        hint, evaluation_path, sub, mix))}
            chosen = match[0]
            if chosen.get("root_index") is None:
                return {"resolved": False, "source": hint, "reason": (
                    "resolve={0} 的样本缺 root_index：指定旧根无法解析，具名拒绝".format(
                        hint))}
            index = int(chosen["root_index"])
            source = hint
            if row.get("root_seed") is None and chosen.get("root_seed") is not None:
                row = dict(row, root_seed=int(chosen["root_seed"]))
    if index is None:
        return {"resolved": False, "source": source, "reason": (
            "声明未锁定根序号（root_index 缺失且无可用 resolve 提示）：指定旧根重评"
            "无法解析，具名拒绝——不默认成 root000，也不替换成别的根")}
    try:
        index = av_family_root_index(int(index))
    except (TypeError, ValueError) as error:
        return {"resolved": False, "source": source, "reason": str(error)}
    descriptor = av_family_root_descriptor(
        prefix_source=prefix_source, sub_scenario=sub, opponent_mix=mix,
        panel_seed=panel_seed, root_index=index)
    declared_seed = row.get("root_seed")
    if isinstance(declared_seed, int) and int(declared_seed) != int(descriptor["root_seed"]):
        return {"resolved": False, "source": source, "reason": (
            "声明里的实际种子与冻结描述符不符（{0} != {1}）：不等价复现，具名拒绝").format(
                int(declared_seed), int(descriptor["root_seed"]))}
    return {"resolved": True, "source": source, "root_index": index,
            "root_id": str(descriptor["root_id"]),
            "root_seed": int(descriptor["root_seed"]),
            "descriptor": dict(descriptor),
            "purpose": row.get("purpose"),
            "seats_per_root": int(row.get("seats_per_root") or 1)}


def av_family_reevaluation_obligations(*, state: Mapping[str, Any], run_root: Path,
                                       registry: Mapping[str, Any], channel: str,
                                       products: Optional[Sequence[Mapping[str, Any]]] = None,
                                       entries: Optional[Mapping[str, Any]] = None,
                                       budget: Optional[float] = None,
                                       ) -> Dict[str, Any]:
    """重评声明 → **比较义务**（候选 × 根 × 臂）：必须被评价的共同根边。

    判定（逐条具名留痕，不静默丢弃）：

      1. 逐行解析冻结描述符（av_family_reevaluation_resolve_root）；解析不出来即
         rejected（AV_FAMILY_REEVAL_UNRESOLVED_ROOT，属"见证/身份不足"一类）；
      2. 该根必须**已登记**（registry 有该（子场景|情景|根身份）的复现参数）：未登记即
         rejected（root_not_registered——不猜 panel_seed/根序号）；见证结论取自 P11 解析
         结果的 witness.status（非 hit 即 witness_insufficient，属 INSUFFICIENT）；
      3. 对每个目标候选（当前候选 + 在案家族席位）按**逐键覆盖**看该根是否已有可核评价：
         已覆盖的记 covered（**不重复计费**、不重跑），未覆盖的进 obligations；
      4. 预算门（**早于费用**）：义务所需根·次超过剩余预算 → 全部记为
         budget_insufficient（不花一张桌、不伪造完成）。
    """

    rows = _av_family_reevaluation_rows(state)
    registry_cells = dict(registry.get("cells") or {})
    archive_mod = av_archive()
    targets = [str(state["identity"]["candidate_id"])]
    for cid in sorted((state.get("archive") or {}).get("seats", {}).get(channel) or ()):
        if str(cid) not in targets:
            targets.append(str(cid))
    resolved_rows: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    witness_insufficient: List[Dict[str, Any]] = []
    for position, row in enumerate(rows):
        parsed = av_family_reevaluation_resolve_root(state, run_root, row)
        base = {"position": position, "sub_scenario": row.get("sub_scenario"),
                "opponent_mix": row.get("opponent_mix"),
                "panel_seed": row.get("panel_seed"),
                "intent": AV_FAMILY_REFRESH_INTENT_REEVALUATE,
                "declared_root_index": row.get("root_index"),
                "resolve": row.get("resolve")}
        if not parsed.get("resolved"):
            rejected.append(dict(base, code=AV_FAMILY_REEVAL_UNRESOLVED_ROOT,
                                 reason=parsed.get("reason")))
            continue
        base.update({"root_id": parsed["root_id"], "root_index": parsed["root_index"],
                     "root_seed": parsed["root_seed"], "purpose": parsed.get("purpose"),
                     "root_descriptor": dict(parsed["descriptor"])})
        cell = registry_cells.get("{0}|{1}|{2}".format(base["sub_scenario"],
                                                      base["opponent_mix"],
                                                      parsed["root_id"]))
        if cell is None:
            rejected.append(dict(base, code="root_not_registered", reason=(
                "该根未登记复现参数（不猜 panel_seed/根序号）：重评不可调度，具名拒绝")))
            continue
        witness = None
        for item in ((state.get("family_refresh_resolved") or {}).get("resolved")
                     or ()):
            if (str(item.get("root_id")) == parsed["root_id"]
                    and str(item.get("sub_scenario") or "") == str(base["sub_scenario"])
                    and str(item.get("opponent_mix") or "") == str(base["opponent_mix"])):
                witness = item.get("witness")
                break
        if isinstance(witness, Mapping) and str(witness.get("status") or "") != "hit":
            witness_insufficient.append(dict(base, code=AV_FAMILY_REEVAL_WITNESS_INSUFFICIENT,
                                             witness=dict(witness), reason=(
                "该根在本迭代的见证结论不是 hit（{0}）：见证不足，记 INSUFFICIENT，"
                "不排评价、不宣告完成").format(witness.get("status"))))
            continue
        base["witness"] = dict(witness) if isinstance(witness, Mapping) else None
        base["registered"] = dict(cell)
        resolved_rows.append(base)
    core_rows: List[Dict[str, Any]] = []
    for item in resolved_rows:
        row = {"root_id": item["root_id"], "sub_scenario": item["sub_scenario"],
               "opponent_mix": item["opponent_mix"], "root_index": item["root_index"],
               "panel_seed": item["panel_seed"], "root_seed": item["root_seed"]}
        row["key"] = _av_family_core_key(row)
        core_rows.append(row)
    obligations: List[Dict[str, Any]] = []
    covered: List[Dict[str, Any]] = []
    for cid in targets:
        coverage = av_family_core_coverage(
            core_rows=core_rows, entry=(entries or {}).get(cid), candidate_id=cid,
            products=products)
        for item, key_row in zip(resolved_rows, coverage["keys"]):
            row = dict(item, candidate_id=cid,
                       token="{0}|{1}|{2}".format(item["sub_scenario"],
                                                  item["opponent_mix"],
                                                  item["root_id"]),
                       key=key_row["key"], arms=key_row["arms"])
            if key_row["covered"]:
                covered.append(dict(row, status="covered", reason=(
                    "该（候选 × 根 × 臂）已有可核评价：不重复计费、不重跑")))
                continue
            obligations.append(dict(row, status="pending",
                                    missing_arms=key_row["uncovered_arms"],
                                    planned_tables=AV_TABLES_PER_FAMILY_EVALUATION,
                                    reason=("重评声明 = 比较义务：该（候选 × 根 × 臂）尚无"
                                            "可核评价，必须排评价")))
    stop_reason: Optional[str] = None
    pending = [item for item in obligations]
    if not rows:
        stop_reason = AV_FAMILY_REEVAL_NO_DECLARATION
        pending = []
    elif not resolved_rows and rejected:
        stop_reason = AV_FAMILY_REEVAL_UNRESOLVED_ROOT
        pending = []
    elif not resolved_rows and witness_insufficient:
        stop_reason = AV_FAMILY_REEVAL_WITNESS_INSUFFICIENT
        pending = []
    elif witness_insufficient and not pending:
        stop_reason = AV_FAMILY_REEVAL_WITNESS_INSUFFICIENT
    elif not pending and obligations and covered:
        # 全部义务已覆盖（本迭代或前序迭代）：无待评价项。
        stop_reason = None
    if budget is not None and (len(pending) + len(covered)) > int(budget):
        stop_reason = AV_FAMILY_REEVAL_BUDGET_INSUFFICIENT
    return {
        "schema": AV_FAMILY_REEVALUATION_SCHEMA, "channel": channel,
        "declared": len(rows), "resolved": len(resolved_rows),
        "targets": list(targets), "obligations": obligations,
        "covered": covered, "rejected": rejected,
        "witness_insufficient": witness_insufficient,
        "pending_tokens": sorted({"{0}|{1}".format(item["candidate_id"], item["token"])
                                  for item in pending}),
        "missing_by_candidate": {},
        "stop_reason": stop_reason,
        "note": ("重评声明 = 比较义务（裁定 §3 第 3 步）：声明被见证不等于被评价；"
                 "补根步必须为缺失的共同根边排评价，且不得因为「没有待发现的新根」"
                 "而整批跳过。逐格配额/预算门/身份面/原子提交语义一律不放宽"),
    }


def _av_family_keep_reason(commit_status: str,
                           rounds: Sequence[Mapping[str, Any]], *,
                           token_ok: bool,
                           declaration_stop: Optional[str] = None) -> str:
    """家族补根保席的**停因**：预算/未授权/不可调度/证据不全分开记，不混谈。"""

    last = dict(rounds[-1]) if rounds else {}
    if commit_status == "budget_insufficient":
        return "budget_insufficient"
    # P9：声明解析凑不齐可见证根（预算门内的有界搜索已停）⇒ 具名停因。它与
    # batch_invalid 分开记：前者是"这一格没有可见证的根可用"，后者是"批本身不合规"。
    if declaration_stop:
        return "declaration_unfillable"
    if commit_status == "epoch_incomplete":
        return "unschedulable"
    if commit_status in ("batch_invalid", "refresh_rejected"):
        return "batch_invalid"
    if commit_status in ("identity_conflict", "declaration_conflict"):
        return "identity_conflict"
    if commit_status in ("not_promising", "no_refresh_requested"):
        return "not_promoting"
    # P8：某一轮因**连续无进展**而停止重试该根（该轮不再花钱）⇒ 具名停因；
    # 与"轮数耗尽"分开记（后者是"每轮都有进展但没补完"），与预算不足分开记。
    if any(row.get("no_progress_stopped") for row in rounds):
        return "family_refill_no_progress"
    if not token_ok and last.get("missing"):
        return "unauthorized"
    if last.get("skipped"):
        return "budget_insufficient"
    if last.get("filled"):
        return "evidence_incomplete"
    if len(rounds) >= AV_REFRESH_FILL_MAX_ROUNDS and last.get("missing"):
        return "rounds_exhausted"
    return "unschedulable"


def _av_family_coverage_completion(state: Mapping[str, Any], run_root: Path,
                                    channel: str, *,
                                    registry: Optional[Mapping[str, Any]],
                                    outcome: Optional[Mapping[str, Any]] = None,
                                    rounds: Sequence[Mapping[str, Any]] = (),
                                    attempts: Sequence[Mapping[str, Any]] = (),
                                    refused: Optional[BaseException] = None
                                    ) -> Dict[str, Any]:
    """补根调度**收口时**的逐键覆盖**完成读数**（重算后落盘；不参与调度与费用判定）。

    P16-FU（run7 实测）：旧实现只在补根轮**开始时**写一份"覆盖"文件、轮末不刷新——
    一个名字像完成读数、内容却是开始快照的文件（run7 该文件只记 root000 两条边，
    而 family_fill.attempts 显示 8 根已真实评价 32 桌）。现在名字与语义分开：

      - 轮首工作项快照 → `archive/family-core-coverage-workitem.json`（排评价用）；
      - 收口完成读数   → `archive/family-core-coverage.json`（本函数，重算后的真实覆盖）。

    **只读重算**：不写运行目录里的其它文件、**不创建冻结清单**（冻结件不存在时按推导读）、
    不改任何调度判据；重算不出来时把缺口写进产物（ok=False + problems），不抛穿调用方。
    """

    run_root = Path(run_root)
    archive_dir = run_root / "archive"
    payload: Dict[str, Any] = {
        "schema": AV_FAMILY_CORE_COVERAGE_SCHEMA,
        "channel": channel, "iteration_no": state.get("iteration_no"),
        "phase": "completion", "is_completion_reading": True,
        "at_utc": utc_now(), "rounds": len(list(rounds or ())),
        "attempts": {
            "total": len(list(attempts or ())),
            "by_status": {str(status): sum(
                1 for item in (attempts or ())
                if str((item or {}).get("status") or "") == str(status))
                for status in sorted({str((item or {}).get("status") or "")
                                      for item in (attempts or ())})}},
        "ok": True, "problems": [],
        "note": ("补根调度**收口时**重算的逐键覆盖（完成读数）：需求集合 = 冻结核心根清单"
                 "（缺冻结件时按当前推导读，且**不因此冻结**）；轮首工作项快照另存 "
                 "archive/{0}").format(AV_FAMILY_CORE_WORKITEM_FILENAME),
    }
    if refused is not None:
        payload.update({
            "ok": False,
            "problems": [{
                "code": "core_list_unavailable_at_completion",
                "stop_reason": getattr(refused, "stop_reason", None),
                "path": getattr(refused, "path", None),
                "problems": list(getattr(refused, "problems", ()) or ()),
                "reason": ("收口时冻结核心根清单不可用：本轮没有可核的完成读数"
                           "（不得沿用上一轮的完成读数冒充本轮）")}],
            "coverage": {}, "missing_comparison": {}, "missing_effective": {}})
    elif registry is None:
        payload.update({
            "ok": False,
            "problems": [{"code": "registry_view_missing",
                          "reason": ("本轮没有登记表视图（补根轮未产出 registry）："
                                     "完成读数不可算，如实标注")}],
            "coverage": {}, "missing_comparison": {}, "missing_effective": {}})
    else:
        freeze_path = archive_dir / "family-core-roots.json"
        try:
            core_list = av_family_core_root_list(
                channel=channel, registry=registry,
                freeze_path=(freeze_path if freeze_path.is_file() else None))
        except FamilyCoreListRefused as error:
            payload.update({
                "ok": False,
                "problems": [{
                    "code": "core_list_unavailable_at_completion",
                    "stop_reason": error.stop_reason, "path": error.path,
                    "problems": list(error.problems),
                    "reason": "收口时冻结核心根清单不可用：无法给出可核的完成读数"}],
                "coverage": {}, "missing_comparison": {}, "missing_effective": {}})
            core_list = None
        if core_list is not None:
            products = _av_family_evaluation_products(run_root)
            entries_now = dict((_av_previous_archive(state, run_root).get("entries")) or {})
            reported_missing = {str(cid): list(tokens or ())
                                for cid, tokens in
                                ((outcome or {}).get("missing") or {}).items()}
            seats = list((((state.get("archive") or {}).get("seats") or {})
                          .get(channel)) or ())
            targets = sorted(set([str(state["identity"]["candidate_id"])]
                                 + [str(cid) for cid in seats]
                                 + list(reported_missing)))
            coverage = {cid: av_family_core_coverage(
                core_rows=core_list["roots"], entry=entries_now.get(cid),
                candidate_id=cid, products=products) for cid in targets}
            comparison = {cid: _av_family_core_coverage_vs_reported(
                coverage=coverage[cid], reported=reported_missing.get(cid) or ())
                for cid in targets}
            missing_effective = {
                cid: sorted(set(coverage[cid]["missing_tokens"])
                            | set(comparison[cid]["reported_only"]))
                for cid in targets}
            payload.update({
                "core_list": {"schema": AV_FAMILY_CORE_LIST_SCHEMA,
                              "source": core_list["source"],
                              "path": core_list["path"],
                              "n_roots": core_list["n_roots"],
                              "created": core_list.get("created"),
                              "view_complete": core_list.get("view_complete"),
                              "conflicts": list(core_list["conflicts"] or ())},
                "coverage": {cid: coverage[cid] for cid in targets},
                "missing_comparison": comparison,
                "missing_effective": missing_effective,
                "n_roots_covered_total": sum(coverage[cid]["n_roots_covered"]
                                             for cid in targets),
                "n_edges_covered_total": sum(coverage[cid]["n_edges_covered"]
                                             for cid in targets)})
    try:
        av_atomic_write_json(archive_dir / AV_FAMILY_CORE_COVERAGE_FILENAME, payload)
        payload["written"] = True
    except OSError as error:
        payload["written"] = False
        payload["problems"] = list(payload["problems"]) + [{
            "code": "coverage_completion_write_failed",
            "reason": "完成读数落盘失败：{0}".format(error)}]
    return payload


def _av_family_fill(state: Dict[str, Any], run_root: Path,
                    ledger: "ActionValueLedger",
                    authorization: Optional[Mapping[str, Any]],
                    test_runtime_factory: Optional[
                        Callable[[], Mapping[str, Any]]] = None
                    ) -> Optional[Dict[str, Any]]:
    """家族通道补根调度（REFRESH_PENDING 家族分支）：声明物化 + 缺失根补根 → 重试提交。

    每轮都由**家族挑战自己的 missing / 声明批**驱动（不自行扩大评价面）；补根只
    补证据（entries 的 family_evaluations），换席仍只由 apply_challenge 的提交分支
    决定。终态可读：committed → 换家族席换家族 epoch；否则保原席原 epoch 并写明确
    停因。幂等：可被反复调用（进程被杀后恢复走同一入口），已完成的（身份 × 子场景
    × 情景 × 根）经检查点复用，不重跑、不重复计费。
    """

    channel = _av_family_declared_channel(state)
    if channel is None:
        return None
    allowed, scope = av_family_scope_allows(channel)
    if not allowed:
        # —— S4：调度**明确跳过**未启用家族：不补根、不评价、不写 epoch、不产生样本 ——
        skip = {"status": "skipped_inactive_family", "channel": channel,
                "refresh_status": AV_FAMILY_INACTIVE_STOP_REASON,
                "stop_reason": AV_FAMILY_INACTIVE_STOP_REASON,
                "scope": scope, "missing": {}, "epoch_kept": None,
                "seats_after": list(((state.get("archive") or {}).get("seats") or {})
                                    .get(channel) or []),
                "samples_or_epoch_produced": False,
                "note": ("S4：家族 {0} 在本版显式 inactive（{1}）；调度跳过——"
                         "该族不产生任何样本或 epoch，缺失也不当 0").format(
                             channel, scope["reason"])}
        state["family_scope"] = scope
        state["family_fill"] = {"schema": AV_FAMILY_FILL_TX_SCHEMA,
                                "attempts": [], "productions": [],
                                "skipped": [dict(scope, status="skipped_inactive_family")],
                                "outcome": skip}
        state["stop_reason"] = AV_FAMILY_INACTIVE_STOP_REASON
        _av_tx_write(Path(state["iter_dir"]), "family_refresh", {
            "schema": "sitin-av-tx-family-refresh/1", "channel": channel,
            "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
            "candidate_id": (state.get("identity") or {}).get("candidate_id"),
            "outcome": "skipped_inactive_family", "scope": scope,
            "note": ("S4：未启用家族被调度跳过（具名原因见 scope.reason）；"
                     "未启动任何桌赛、未建立 epoch、未产生样本")})
        av_state_history_append(state, "REFRESH_PENDING",
                                "家族通道被跳过：本版未启用该族（S4）",
                                channel=channel, skip_status="skipped_inactive_family")
        return skip
    # P16-C5：冻结核心根清单不可用（不可读/不合法/身份不符/写不进去）时的**具名停止**；
    # 在补根轮内捕获、循环后收口（保留原件、不重定需求集合、不继续推进/提交）。
    core_list_stop: Optional[FamilyCoreListRefused] = None
    # P16-FU：收口完成读数用的**最后一轮登记表视图**（只读；不重新写台账）。
    registry_view: Optional[Mapping[str, Any]] = None
    # P16-FU：本通道 epoch 的核心根声明（需求集合推导的第二来源；每轮只读一次）。
    epoch_now: Mapping[str, Any] = (_av_family_inherited_epochs(
        state, Path(run_root))[0].get(channel) or {})
    fill = state.setdefault("family_fill", {"schema": AV_FAMILY_FILL_TX_SCHEMA,
                                            "attempts": [], "productions": []})
    fill["schema"] = AV_FAMILY_FILL_TX_SCHEMA
    fill.setdefault("attempts", [])
    fill.setdefault("productions", [])
    # —— Q6：统一受信授权校验（家族补根 = 真实桌赛；未通过即不动一张桌）——
    token_ok, auth_refusal, auth_audit = av_authorization_allows(
        authorization, operation="family_fill",
        required=AV_AUTHORIZATION_OPERATION_REQUIREMENTS["family_fill"])
    fill["authorization"] = auth_audit
    state["authorization"] = auth_audit
    rounds: List[Dict[str, Any]] = []
    outcome = _av_commit_family(state, run_root, attempt_refresh=True,
                                budget=_av_refresh_budget(ledger))
    for round_no in range(1, AV_REFRESH_FILL_MAX_ROUNDS + 1):
        status = str(outcome.get("status") or "")
        row: Dict[str, Any] = {
            "round": round_no, "status": status, "phase": outcome.get("phase"),
            "missing": dict(outcome.get("missing") or {}),
            "unmaterialized": list(outcome.get("unmaterialized") or []),
            "filled": [], "blocked": list(outcome.get("blocked") or []),
            "skipped": [], "budget": _av_refresh_budget(ledger),
            "remaining_tables_full": (ledger.remaining("tables_full")
                                      if ledger is not None else None)}
        rounds.append(row)
        # —— P15：先算**重评义务**（比较义务独立于「有没有待发现的新根」）——
        # 声明被见证 ⇒ unmaterialized 为空 ⇒ 提交结局不再是 pending；若此时直接 break，
        # 这批声明就永远不会变成评价（run6 实测：9 条声明见证后仍 0/16 边）。
        recorded = _av_record_family_roots(run_root, state)
        registry = _av_family_root_registry(recorded["channels"])
        registry_view = registry
        row["blocked"] = row["blocked"] + list(recorded["conflicts"])
        products = _av_family_evaluation_products(run_root)
        entries_now = dict((_av_previous_archive(state, run_root).get("entries")) or {})
        obligations = av_family_reevaluation_obligations(
            state=state, run_root=run_root, registry=registry, channel=channel,
            products=products, entries=entries_now,
            budget=_av_refresh_budget(ledger))
        fill["reevaluation"] = obligations
        row["reevaluation"] = {
            "schema": AV_FAMILY_REEVALUATION_SCHEMA,
            "declared": obligations["declared"],
            "resolved": obligations["resolved"],
            "obligations": len(obligations["obligations"]),
            "covered": len(obligations["covered"]),
            "rejected": list(obligations["rejected"]),
            "witness_insufficient": list(obligations["witness_insufficient"]),
            "stop_reason": obligations["stop_reason"],
            "tokens": [item["token"] for item in obligations["obligations"]]}
        pending_obligations = list(obligations["obligations"])
        if status != "pending" and not pending_obligations:
            # 既没有待补齐的提交项、也没有待评价的重评义务：这才是"没有事可做"。
            break
        if not token_ok:
            row["note"] = ("家族补根是真实桌赛：需要**受信**授权（Q6 统一校验未"
                           "通过：{0}）；未取得即不动一张桌").format(auth_refusal)
            break
        # —— P1：缺失集合 = **冻结核心根清单逐键覆盖**（不是"当时的行集合"、也不是行数）——
        # P16-C5：清单不可用即**具名停止**（保留原件；绝不在运行中重定需求集合）。
        try:
            core_list = av_family_core_root_list(
                channel=channel, registry=registry,
                freeze_path=Path(run_root) / "archive" / "family-core-roots.json",
                # P16-FU：需求集合 = 完整核心矩阵声明（登记表 + 本通道 epoch 核心根）。
                epoch_rows=list((epoch_now or {}).get("roots") or ()))
        except FamilyCoreListRefused as error:
            core_list_stop = error
            row["blocked"] = list(row["blocked"]) + [{
                "phase": "core_list_invalid", "stop_reason": error.stop_reason,
                "path": error.path, "problems": list(error.problems),
                "reason": ("冻结核心根清单不可用：停止（保留原件；运行中不得自动重定"
                           "需求集合）")}]
            break
        reported_missing = {str(cid): list(tokens or ())
                            for cid, tokens in (outcome.get("missing") or {}).items()}
        # P15：重评义务的目标候选（当前候选 + 在案家族席位）也在覆盖目标里——
        # 否则下面按候选并集取 missing 时会缺键（义务可能落在在席者身上）。
        coverage_targets = sorted(set(
            [str(state["identity"]["candidate_id"])] + list(reported_missing)
            + [str(item["candidate_id"]) for item in pending_obligations]))
        coverage = {cid: av_family_core_coverage(
            core_rows=core_list["roots"], entry=entries_now.get(cid),
            candidate_id=cid, products=products) for cid in coverage_targets}
        comparison = {cid: _av_family_core_coverage_vs_reported(
            coverage=coverage[cid], reported=reported_missing.get(cid) or ())
            for cid in coverage_targets}
        row["blocked"] = row["blocked"] + [
            dict(item, reason="冻结核心根清单与登记表不一致（以冻结件为准）",
                 phase="core_list_conflict") for item in core_list["conflicts"]]
        row["core_list"] = {"schema": AV_FAMILY_CORE_LIST_SCHEMA,
                            "source": core_list["source"],
                            "path": core_list["path"],
                            "n_roots": core_list["n_roots"],
                            "created": core_list.get("created"),
                            # P16-FU：视图是否完整（不完整 = 本轮按推导读、**不冻结**）；
                            # deferred 具名说明"为什么还没冻结"（缺哪些格）。
                            "view_complete": core_list.get("view_complete"),
                            "deferred": core_list.get("deferred"),
                            "conflicts": core_list["conflicts"]}
        row["core_coverage"] = {cid: {
            "n_roots": coverage[cid]["n_roots"],
            "n_roots_covered": coverage[cid]["n_roots_covered"],
            "n_edges": coverage[cid]["n_edges"],
            "n_edges_covered": coverage[cid]["n_edges_covered"],
            "missing_keys": coverage[cid]["missing_keys"]} for cid in coverage_targets}
        row["missing_comparison"] = comparison
        # 工作项用逐键缺失 ∪ 生产自报 ∪ **重评义务**（差额具名：一条不丢）。
        # P15：重评义务即使在"没有待发现新根"时也要进工作项——声明的是比较义务。
        obligation_tokens: Dict[str, List[str]] = {}
        for item in pending_obligations:
            obligation_tokens.setdefault(str(item["candidate_id"]), []).append(
                str(item["token"]))
        missing_effective = {
            cid: sorted(set(coverage[cid]["missing_tokens"])
                        | set(comparison[cid]["reported_only"])
                        | set(obligation_tokens.get(cid) or ()))
            for cid in sorted(set(list(coverage_targets) + list(obligation_tokens)))}
        try:
            # P16-FU：这里落的是**工作项快照**（排本轮评价用），改名 + 具名标注，
            # 不再占用"完成读数"的文件名；完成读数由本轮收口处重算落盘。
            av_atomic_write_json(
                Path(run_root) / "archive" / AV_FAMILY_CORE_WORKITEM_FILENAME, {
                    "schema": AV_FAMILY_CORE_WORKITEM_SCHEMA,
                    "channel": channel, "iteration_no": state.get("iteration_no"),
                    "round": int(round_no),
                    "phase": "work_item_snapshot", "is_completion_reading": False,
                    "at_utc": utc_now(), "core_list": row["core_list"],
                    "coverage": {cid: coverage[cid] for cid in coverage_targets},
                    "missing_comparison": comparison,
                    "missing_effective": missing_effective,
                    "note": ("**工作项快照**（补根轮开始时排评价用），不是完成读数："
                             "本轮评价完成后覆盖会变化，完成读数见 archive/{0}"
                             "（每次补根调度收口时重算落盘）").format(
                                 AV_FAMILY_CORE_COVERAGE_FILENAME)})
        except OSError:
            pass
        items, blocked = _av_family_fill_items(state=state, outcome=outcome,
                                              registry=registry, channel=channel,
                                              missing_override=missing_effective)
        row["blocked"] = row["blocked"] + list(blocked)
        if not items:
            break
        # —— P8 · 无进展停止（**早于费用**）：同一根连续 K 轮无新证据 → 不再重试该根 ——
        # 判据是可复算事实（逐轮落 row["attempts"]）：该根本轮被真实评价而**既没有新
        # 可用样本、也没有新登记根**。停止只针对该根，同一轮其余工件照常推进。
        no_progress = fill.setdefault("no_progress", {})
        runnable, stopped = _av_family_split_no_progress(
            items, registry=no_progress, round_no=round_no)
        row["no_progress"] = stopped
        row["attempts"] = []
        if not runnable:
            row["note"] = ("本轮全部工件均已连续 {0} 轮无进展：停止重试该批根（不再花"
                           "一次评价的费用），保持原家族席与原家族 epoch").format(
                               AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS)
            row["no_progress_stopped"] = True
            break
        # 整轮预算预检（**早于费用**）：本轮需要的根·次超过剩余预算 → 一张桌都不动，
        # 保持原家族席与原家族 epoch（与 normal 通道 apply_challenge 的预算门同义：
        # 补根花的桌数只有在真的能推进到提交时才值，绝不"花了钱仍保原席"）。
        round_budget = _av_refresh_budget(ledger)
        needed = sum(len(item["root_ids"]) for item in runnable)
        if round_budget is not None and needed > int(round_budget):
            row["needed"] = needed
            row["budget"] = int(round_budget)
            row["skipped"] = [dict(item, budget=int(round_budget),
                                   reason=("家族补根预算不足（整轮预检：需 {0} 根·次 > "
                                           "预算 {1}，早于费用）".format(
                                               needed, int(round_budget))))
                              for item in runnable]
            break
        progressed = False
        budget_limited = False
        for item in runnable:
            source = _av_refresh_participant_source(state, run_root,
                                                    str(item["candidate_id"]))
            if source is None:
                row["blocked"].append(dict(item, reason=(
                    "候选源码不可得（在案摘要不符或无生成产物）：不猜源码、不冒名评价")))
                row["attempts"].append(_av_family_round_fact(
                    item, round_no=round_no, attempted=False,
                    reason="候选源码不可得（未评价，不计入无进展）"))
                continue
            budget = _av_refresh_budget(ledger)
            remaining = ledger.remaining("tables_full") if ledger is not None else None
            if budget is not None and len(item["root_ids"]) > int(budget):
                row["skipped"].append(dict(item, reason="家族补根预算不足（根·次）",
                                           budget=budget))
                budget_limited = True
                row["attempts"].append(_av_family_round_fact(
                    item, round_no=round_no, attempted=False,
                    reason="家族补根预算不足（根·次，未评价，不计入无进展）"))
                continue
            if remaining is not None and float(item["planned_tables"]) > float(remaining):
                row["skipped"].append(dict(item, reason="剩余 tables_full 不足",
                                           remaining=remaining))
                budget_limited = True
                row["attempts"].append(_av_family_round_fact(
                    item, round_no=round_no, attempted=False,
                    reason="剩余 tables_full 不足（未评价，不计入无进展）"))
                continue
            result = _av_family_run_evaluation(state, run_root, ledger, authorization,
                                              item, source, test_runtime_factory)
            fill["attempts"].append(result["attempt"])
            if result.get("evaluation") is None:
                row["skipped"].append({"candidate_id": item["candidate_id"],
                                       "sub_scenario": item["sub_scenario"],
                                       "opponent_mix": item["opponent_mix"],
                                       "token": item["token"],
                                       "reason": result.get("reason")})
                # 事实：本轮**真的评价过**该根，但没拿到可用证据 ⇒ 记一次无进展；
                # 被预算/源码挡在评价之外的工件**不**计入（那是"没花钱"，不是"花了两遍"）。
                row["attempts"].append(_av_family_round_fact(
                    item, round_no=round_no, attempted=True, evidence_added=False,
                    status=str(result["attempt"].get("status")),
                    reason=result.get("reason")))
                continue
            merge = _av_family_merge_fills(
                state, run_root, {str(item["candidate_id"]): (item, result)})
            report = merge.get(str(item["candidate_id"])) or {}
            # A2：已登记根的判据是**完整根身份**（含情景/种子），不是裸根名——
            # 旧实现的裸根名集合会把 H 与 M、跨种子同索引的根压成一条（8 → 4）。
            already = {_av_family_root_identity_key(row)
                       for row in fill["productions"]}
            appended = 0
            for root_id in item["root_ids"]:
                production = {
                    "candidate_id": item["candidate_id"],
                    "sub_scenario": item["sub_scenario"],
                    "opponent_mix": item["opponent_mix"],
                    "panel_seed": item["panel_seed"],
                    "root_index": (item["root_indexes"][0]
                                   if item["root_indexes"] else None),
                    "root_id": root_id, "seats_per_root": item["seats_per_root"],
                    "root_seed": item.get("root_seed"),
                    "root_descriptor": item.get("root_descriptor"),
                    "kind": item.get("kind")}
                key = _av_family_root_identity_key(production)
                if key in already:
                    continue        # 已登记的根不重复登记（同一根只有一份复现参数）
                already.add(key)
                fill["productions"].append(production)
                appended += 1
            row["filled"].append({
                "candidate_id": item["candidate_id"], "kind": item.get("kind"),
                "sub_scenario": item["sub_scenario"],
                "opponent_mix": item["opponent_mix"],
                "panel_seed": item["panel_seed"], "roots": list(item["root_ids"]),
                "reuse": result["attempt"].get("reuse"),
                "tables_executed": result["attempt"].get("tables_executed"),
                "roots_added": list(report.get("roots_added") or []),
                "merge": report})
            # 净进展 = **真的补进根证据**（或新登记根）；面板跑了但结果被复用/
            # 整根失效都不算进展，否则会在同一 missing 上空转（假装推进）。
            row["attempts"].append(_av_family_round_fact(
                item, round_no=round_no, attempted=True,
                evidence_added=bool(report.get("roots_added")) or bool(appended),
                status="completed", reason="",
                roots_added=report.get("roots_added") or (),
                n_samples=report.get("n_samples")))
            progressed = (progressed or bool(report.get("roots_added"))
                          or bool(appended))
        # —— 逐轮无进展结算（**事实判定**，可复算）：有进展即清零，否则计数 +1 ——
        for fact in row.get("attempts") or []:
            key = str(fact["root_key"])
            if fact.get("evidence_added"):
                no_progress.pop(key, None)
                continue
            if not fact.get("attempted"):
                continue
            record = no_progress.setdefault(key, {
                "root_id": key, "root_seed": fact.get("root_seed"),
                "sub_scenario": fact.get("sub_scenario"),
                "opponent_mix": fact.get("opponent_mix"),
                "panel_seed": fact.get("panel_seed"),
                "root_index": fact.get("root_index"),
                "rounds": 0, "first_round": int(round_no)})
            record["rounds"] = int(record.get("rounds") or 0) + 1
            record["last_round"] = int(round_no)
            record["last_reason"] = fact.get("reason")
        # 本轮结束后判定**停止重试**：本轮无任何进展，且（本轮开始时已有根在停止名单里，
        # 或本轮结束时已有根累计到 K 轮无进展）⇒ 具名停因收尾（该轮不再花钱）。
        # 预算受限的轮次不算（预算停因仍由既有 budget_insufficient 分支负责，不削弱）。
        maxed = sorted(str(key) for key, value in (no_progress or {}).items()
                       if int(value.get("rounds") or 0)
                       >= AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS)
        if not progressed and not budget_limited and (stopped or maxed):
            if maxed and not stopped:
                row["no_progress"] = [
                    dict((no_progress or {})[key], stop_reason="family_refill_no_progress",
                         note=("本轮结束时有 {0} 个根累计到 {1} 轮无进展：停止重试"
                               "（下一轮不再为它们付费）").format(
                                   len(maxed), AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS))
                    for key in maxed]
            row["no_progress_stopped"] = True
            break
        if not progressed:
            break
        outcome = _av_commit_family(state, run_root, attempt_refresh=True,
                                    budget=_av_refresh_budget(ledger))
    # —— P16-FU：补根调度**收口完成读数**（重算后落 archive/family-core-coverage.json）——
    # 名字与语义分开：轮首工作项快照在 *-workitem.json，本文件才是"这一轮结束后覆盖到哪"。
    # 纯读数：不参与调度/费用判定；冻结件不可用时如实记 ok=False（不沿用旧读数）。
    fill["coverage_completion"] = _av_family_coverage_completion(
        state, run_root, channel, registry=registry_view, outcome=outcome,
        rounds=rounds, attempts=list(fill.get("attempts") or ()),
        refused=core_list_stop)
    if core_list_stop is not None:
        # —— P16-C5 收口：具名停止（不提交、不换席、不重定需求集合）；账目如实落盘 ——
        state["stop_reason"] = core_list_stop.stop_reason
        archive_after = _av_previous_archive(state, run_root)
        seats_after = list(((archive_after.get("slots") or {}).get(channel)) or [])
        verdict = {
            "status": "core_list_invalid", "channel": channel,
            "terminal": "INPUT_GAP", "stop_reason": core_list_stop.stop_reason,
            "path": core_list_stop.path, "problems": list(core_list_stop.problems),
            "seats_after": seats_after,
            "reevaluation": {
                "schema": AV_FAMILY_REEVALUATION_SCHEMA,
                "declared": int((fill.get("reevaluation") or {}).get("declared") or 0),
                "resolved": int((fill.get("reevaluation") or {}).get("resolved") or 0),
                "obligations": len((fill.get("reevaluation") or {}).get("obligations") or ()),
                "covered": len((fill.get("reevaluation") or {}).get("covered") or ()),
                "rejected": list((fill.get("reevaluation") or {}).get("rejected") or ()),
                "witness_insufficient": list(
                    (fill.get("reevaluation") or {}).get("witness_insufficient") or ()),
                "stop_reason": (fill.get("reevaluation") or {}).get("stop_reason")},
            "note": ("冻结核心根清单不可用（{0}）：具名停止并保留原件——不得按当前推导"
                     "重写需求集合、不得继续补根/提交").format(core_list_stop.stop_reason)}
        fill["outcome"] = verdict
        _av_tx_write(Path(state["iter_dir"]), "family_refresh", {
            "schema": "sitin-av-tx-family-refresh/1", "channel": channel,
            "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
            "candidate_id": state["identity"]["candidate_id"],
            "rounds": [dict(row) for row in rounds], "outcome": dict(verdict),
            "seats_after": seats_after})
        return verdict
    status = str(outcome.get("status") or "")
    archive_after = _av_previous_archive(state, run_root)
    seats_after = list(((archive_after.get("slots") or {}).get(channel)) or [])
    # A4：本步的事务件同时记下被挑战通道的席位与**探索席**（探索席不在冻结面内，
    # 由公共行为面板决定）——补根步重写事务件时不丢这项读数。
    exploration_after = list(
        ((archive_after.get("slots") or {}).get("exploration")) or [])
    archive_path = str(Path(run_root) / "archive" / "av-archive.json")
    if status == "committed":
        verdict = {"status": "committed", "channel": channel,
                   "refresh_status": "committed",
                   # P15：重评义务账目在提交路径上也如实落（声明数 / 义务数 / 结论）。
                   "reevaluation": {
                       "schema": AV_FAMILY_REEVALUATION_SCHEMA,
                       "declared": int((fill.get("reevaluation") or {}).get("declared") or 0),
                       "resolved": int((fill.get("reevaluation") or {}).get("resolved") or 0),
                       "obligations": len((fill.get("reevaluation") or {}).get(
                           "obligations") or ()),
                       "covered": len((fill.get("reevaluation") or {}).get("covered") or ()),
                       "rejected": list((fill.get("reevaluation") or {}).get("rejected") or ()),
                       "witness_insufficient": list(
                           (fill.get("reevaluation") or {}).get(
                               "witness_insufficient") or ()),
                       "stop_reason": (fill.get("reevaluation") or {}).get("stop_reason")},
                   "epoch_after": outcome.get("epoch_after"),
                   "seats_after": seats_after,
                   "stop_reason": AV_FAMILY_COMMITTED_STOP_REASON,
                   "note": ("全员在家族旧根 + 刷新根齐备 → 原子提交新家族 epoch 并"
                            "统一重排家族席（补根只补证据，换席仍只由 apply_challenge "
                            "提交分支决定）")}
        fill["outcome"] = verdict
        state["stop_reason"] = AV_FAMILY_COMMITTED_STOP_REASON
        state["archive"] = {"archive_path": archive_path,
                            "family_refresh_status": "committed",
                            "family_epoch_after": outcome.get("epoch_after"),
                            "seats_kept": False}
        state["identity"]["family_epoch"] = "{0}@epoch-committed".format(channel)
        _av_tx_write(Path(state["iter_dir"]), "family_refresh", {
            "schema": "sitin-av-tx-family-refresh/1", "channel": channel,
            "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
            "candidate_id": state["identity"]["candidate_id"],
            "rounds": [dict(row) for row in rounds], "outcome": dict(verdict),
            "seats_after": seats_after,
            "exploration_after": exploration_after})
        av_state_history_append(state, "ARCHIVE_COMMITTED",
                                "家族补根齐备 → 原子提交新家族 epoch（家族席重排）",
                                channel=channel, family_refresh="committed",
                                seats_after=seats_after)
        return verdict
    if status == "established":
        # A1：首次初始化完成——已声明的核心格补齐 → 建立家族 epoch 1 + 首个家族席
        # （与"挑战成功换 epoch"分开记：这里没有原席可比）。
        epoch_no = (outcome.get("epoch") or {}).get("epoch")
        verdict = {"status": "established", "channel": channel,
                   "refresh_status": "epoch_established",
                   "reevaluation": {
                       "schema": AV_FAMILY_REEVALUATION_SCHEMA,
                       "declared": int((fill.get("reevaluation") or {}).get("declared") or 0),
                       "resolved": int((fill.get("reevaluation") or {}).get("resolved") or 0),
                       "obligations": len((fill.get("reevaluation") or {}).get(
                           "obligations") or ()),
                       "covered": len((fill.get("reevaluation") or {}).get("covered") or ()),
                       "rejected": list((fill.get("reevaluation") or {}).get("rejected") or ()),
                       "witness_insufficient": list(
                           (fill.get("reevaluation") or {}).get(
                               "witness_insufficient") or ()),
                       "stop_reason": (fill.get("reevaluation") or {}).get("stop_reason")},
                   "epoch_after": epoch_no, "seats_after": seats_after,
                   "stop_reason": AV_FAMILY_ESTABLISHED_STOP_REASON,
                   "note": ("家族通道首次初始化：无在案 epoch → 按已声明的核心格补齐"
                            "（两侧 × H/M 齐备）→ 建立 epoch {0} 并落首个家族席"
                            "（无在案席位可比）").format(epoch_no)}
        fill["outcome"] = verdict
        state["stop_reason"] = AV_FAMILY_ESTABLISHED_STOP_REASON
        state["archive"] = {"archive_path": archive_path,
                            "family_refresh_status": "epoch_established",
                            "family_epoch_after": epoch_no, "seats_kept": False}
        state["identity"]["family_epoch"] = "{0}@epoch-established".format(channel)
        _av_tx_write(Path(state["iter_dir"]), "family_refresh", {
            "schema": "sitin-av-tx-family-refresh/1", "channel": channel,
            "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
            "candidate_id": state["identity"]["candidate_id"],
            "rounds": [dict(row) for row in rounds], "outcome": dict(verdict),
            "seats_after": seats_after,
            "exploration_after": exploration_after})
        av_state_history_append(state, "ARCHIVE_COMMITTED",
                                "家族通道首次初始化：核心格补齐 → 建立 epoch（首个家族席）",
                                channel=channel, family_refresh="epoch_established",
                                seats_after=seats_after)
        return verdict
    resolution = state.get("family_refresh_resolved") or {}
    # 没有解析结果（夹具路径 / 旧状态 / 未接线）时**不**产生声明类停因：旧行为逐字不变。
    declaration_stop: Optional[str] = None
    if resolution:
        declaration_stop = (None if resolution.get("complete")
                            else (resolution.get("stop_reason")
                                  or AV_FAMILY_DECLARATION_UNFILLABLE))
    keep = _av_family_keep_reason(status, rounds, token_ok=token_ok,
                                  declaration_stop=declaration_stop)
    stop_reason = AV_FAMILY_KEEP_STOP_REASONS[keep]
    # —— P15：有重评声明时的停因三类可分（**不得**回落到"没有新根可发现"的表述）——
    # ① 预算不足 ② 见证/身份不足（INSUFFICIENT） ③ 义务已评价（提交仍 pending：
    #    保原家族席与原家族 epoch）；只有**确实没有任何重评声明**时才用
    #    AV_FAMILY_REEVAL_NO_DECLARATION。
    reevaluation = fill.get("reevaluation") or {}
    reevaluation_declared = int(reevaluation.get("declared") or 0)
    reevaluation_stop = str(reevaluation.get("stop_reason") or "")
    reevaluation_edges_evaluated = sum(
        1 for row in rounds for item in ((row.get("reevaluation") or {}).get("tokens") or ())
        if item) and any(row.get("filled") for row in rounds)
    if reevaluation_declared > 0:
        if reevaluation_stop == AV_FAMILY_REEVAL_BUDGET_INSUFFICIENT:
            stop_reason = AV_FAMILY_REEVAL_BUDGET_INSUFFICIENT
        elif reevaluation_stop == AV_FAMILY_REEVAL_UNRESOLVED_ROOT:
            stop_reason = AV_FAMILY_REEVAL_UNRESOLVED_ROOT
        elif reevaluation_stop == AV_FAMILY_REEVAL_WITNESS_INSUFFICIENT:
            stop_reason = AV_FAMILY_REEVAL_WITNESS_INSUFFICIENT
        elif reevaluation_edges_evaluated:
            stop_reason = AV_FAMILY_REEVAL_EDGES_PENDING
        else:
            # 声明齐备但没有可排的义务（全部已覆盖）：仍标为"提交未成立"，
            # 不写成 epoch 已刷新、也不写成"没有重评声明"。
            stop_reason = AV_FAMILY_REEVAL_EDGES_EVALUATED
    # 没有任何重评声明时**保持旧停因逐字不变**（发现型计划的既有行为与读数不动）；
    # "无重评声明"这一类的记号仍在 verdict.reevaluation / fill.reevaluation 里如实落，
    # 验收器据此区分三类，而不会把发现型计划的停因改名。
    verdict = {"status": keep, "channel": channel,
               "refresh_status": (outcome.get("refresh") or {}).get("status"),
               "missing": dict(outcome.get("missing") or {}),
               # P8：无进展停止的**具名账目**（根身份 + 轮次 + 最后一次失败原因）；
               # 未发生无进展时为空映射（不隐藏、也不冒充）。
               "no_progress": {str(key): dict(value) for key, value in
                               sorted((fill.get("no_progress") or {}).items())},
               # P9：声明解析（有界独立根搜索）的结论与逐候选根留痕的引用；
               # 未接线/夹具路径为空映射（不冒充"解析过"）。
               "declaration": ({
                   "complete": resolution.get("complete"),
                   "stop_reason": resolution.get("stop_reason"),
                   "cells": (resolution.get("search") or {}).get("cells"),
                   "candidates_tried": (resolution.get("search") or {}).get(
                       "candidates_tried"),
                   "artifact": str(Path(str(state.get("iter_dir") or "")) /
                                   "family-declaration.json"),
               } if resolution else {}),
               "epoch_kept": ((outcome.get("refresh") or {}).get("epoch_kept")),
               # P15：重评义务账目进终态（声明数 / 义务数 / 未评价与具名拒绝逐条）。
               "reevaluation": {
                   "schema": AV_FAMILY_REEVALUATION_SCHEMA,
                   "declared": reevaluation_declared,
                   "resolved": int(reevaluation.get("resolved") or 0),
                   "obligations": len(reevaluation.get("obligations") or ()),
                   "covered": len(reevaluation.get("covered") or ()),
                   "rejected": list(reevaluation.get("rejected") or ()),
                   "witness_insufficient": list(
                       reevaluation.get("witness_insufficient") or ()),
                   "stop_reason": reevaluation.get("stop_reason")},
               "seats_after": seats_after, "stop_reason": stop_reason,
               "note": ("家族补根未齐备：保持原家族席与原家族 epoch（不混新旧均值），"
                        "挑战者留候选池与探索队列；停因见 status；"
                        "重评声明（比较义务）的逐条结论见 reevaluation")}
    fill["outcome"] = verdict
    fill["stop_reason"] = stop_reason
    fill["missing"] = dict(outcome.get("missing") or {})
    fill["next_step"] = ("下一轮迭代按 next_generation_plan 重排；被保席的家族挑战者"
                         "仍在候选池，可在后续迭代重新挑战")
    state["family_fill"] = fill
    state["stop_reason"] = stop_reason
    state["archive"] = {"archive_path": archive_path,
                        "family_refresh_status": status,
                        "family_epoch_kept": verdict["epoch_kept"],
                        "seats_kept": True}
    state["identity"]["family_epoch"] = "{0}@epoch-kept(原家族席保留)".format(channel)
    _av_tx_write(Path(state["iter_dir"]), "family_refresh", {
        "schema": "sitin-av-tx-family-refresh/1", "channel": channel,
        "run_id": state.get("run_id"), "iteration_no": state.get("iteration_no"),
        "candidate_id": state["identity"]["candidate_id"],
        "rounds": [dict(row) for row in rounds], "outcome": dict(verdict),
        "seats_after": seats_after,
        "exploration_after": exploration_after})
    av_state_history_append(state, "ARCHIVE_COMMITTED",
                            "家族补根未齐备：保持原家族席原家族 epoch（{0}）".format(keep),
                            channel=channel, family_refresh=status, seats_kept=True)
    return verdict


def _step_archive(state: Dict[str, Any], run_root: Path,
                  ledger: Optional["ActionValueLedger"] = None) -> Dict[str, Any]:
    outcome = _av_commit_archive(state, run_root, attempt_refresh=True,
                                 refresh_budget=_av_refresh_budget(ledger))
    refresh = outcome.get("refresh") if isinstance(outcome.get("refresh"),
                                                  Mapping) else {}
    state["archive"] = {"archive_path": str(Path(run_root) / "archive" / "av-archive.json"),
                        "refresh_status": (refresh or {}).get("status"),
                        "epoch_kept": (refresh or {}).get("epoch_kept"),
                        "seats_kept": (refresh or {}).get("seats_kept")}
    # —— P7c：家族通道在**同一步**提交/挑战（未声明 family_channel 时零行为变化）——
    family = _av_commit_family(state, run_root, attempt_refresh=True,
                               budget=_av_refresh_budget(ledger))
    family_status = str(family.get("status") or "inactive")
    family_pending = family_status == "pending"
    if family_status != "inactive":
        family_refresh = (family.get("refresh") or {}) if isinstance(
            family.get("refresh"), Mapping) else {}
        state["archive"] = dict(state["archive"],
                                family_refresh_status=(family_refresh.get("status")
                                                       or family_status),
                                family_seats_kept=family_refresh.get("seats_kept"),
                                family_epoch_kept=family_refresh.get("epoch_kept"),
                                family_epoch_after=family.get("epoch_after"))
    if outcome["status"] == "REFRESH_PENDING" or family_pending:
        state["identity"]["panel_epoch"] = "refresh-pending(旧席位保留)"
        # P7b：把挑战点名的缺失根与下一步写进状态（下一推进步自动调度补根）。
        fill = state.setdefault("refresh_fill", {"schema": AV_REFRESH_FILL_TX_SCHEMA,
                                                 "attempts": []})
        fill.setdefault("attempts", [])
        if outcome["status"] == "REFRESH_PENDING":
            fill["missing"] = dict((refresh or {}).get("missing") or {})
            fill["next_step"] = ("为点名缺失的身份补根：按剩余 tables_full 预算复用真实"
                                 "面板装配与 P6 实例台账/检查点执行，补齐后重试提交")
        if family_pending:
            # 家族通道的缺失（声明批/点名根）同样在补根步调度；两个通道的缺失分开记。
            fill["family_missing"] = dict(family.get("missing") or {})
            fill["family_unmaterialized"] = list(family.get("unmaterialized") or [])
            fill["family_next_step"] = ("为家族通道补齐声明批与点名缺失根：按显式根声明"
                                        "调用家族条件评价，齐备后重试家族挑战")
            state["identity"]["family_epoch"] = (
                "{0}@epoch-pending(首个家族席未建立)".format(family.get("channel"))
                if family.get("phase") == "epoch_core_fill" else
                "{0}@refresh-pending(原家族席保留)".format(family.get("channel")))
        av_state_history_append(state, "REFRESH_PENDING",
                                "刷新未全部完成：保持旧 epoch 旧席位（不混新旧均值）",
                                family=(family_status if family_status != "inactive"
                                        else None))
        return {"advanced": "REFRESH_PENDING", "pending": True}
    state["identity"]["panel_epoch"] = ("normal@epoch-committed"
                                        if (refresh or {}).get("status") == "committed"
                                        else "normal@epoch-kept(原席保留)")
    if family_status != "inactive":
        state["identity"]["family_epoch"] = (
            "{0}@epoch-established".format(family.get("channel"))
            if family_status == "established" else
            "{0}@epoch-committed".format(family.get("channel"))
            if family_status == "committed" else
            "{0}@epoch-kept(原家族席保留)".format(family.get("channel")))
    av_state_history_append(state, "ARCHIVE_COMMITTED", "档案原子提交",
                            refresh=(refresh or {}).get("status"),
                            seats_kept=(refresh or {}).get("seats_kept"),
                            family=(family_status if family_status != "inactive"
                                    else None))
    return {"advanced": "ARCHIVE_COMMITTED"}


def _step_refresh_retry(state: Dict[str, Any], run_root: Path,
                        ledger: Optional["ActionValueLedger"] = None) -> Dict[str, Any]:
    """只重试提交、不自行补根的旧入口（P7 语义；状态机自 P7b 起改走 _step_refresh_fill）。

    保留原因：外部脚本/旧状态的"仅重试提交"语义仍可用（不改变任何既有语义），但
    **状态机主链不再经过它**——否则会退回"永远停在 REFRESH_PENDING"的死胡同。
    """

    outcome = _av_commit_archive(state, run_root, attempt_refresh=True,
                                 refresh_budget=_av_refresh_budget(ledger))
    refresh = outcome.get("refresh") if isinstance(outcome.get("refresh"),
                                                  Mapping) else {}
    if outcome["status"] == "REFRESH_PENDING":
        av_state_history_append(state, "REFRESH_PENDING",
                                "刷新仍未补齐：继续保留旧席位（恢复不重复计费）")
        return {"advanced": "REFRESH_PENDING", "pending": True,
                "still_pending": True}
    state["identity"]["panel_epoch"] = ("normal@epoch-committed"
                                        if (refresh or {}).get("status") == "committed"
                                        else "normal@epoch-kept(原席保留)")
    av_state_history_append(state, "ARCHIVE_COMMITTED", "刷新补齐后原子提交",
                            refresh=(refresh or {}).get("status"),
                            seats_kept=(refresh or {}).get("seats_kept"))
    return {"advanced": "ARCHIVE_COMMITTED"}


def _step_batch_end(state: Dict[str, Any], run_root: Path,
                    ledger: "ActionValueLedger") -> Dict[str, Any]:
    iter_dir = Path(state["iter_dir"])
    archive_mod = av_archive()
    archive = json.loads((Path(run_root) / "archive" / "av-archive.json")
                         .read_text(encoding="utf-8"))
    refresh_fill = state.get("refresh_fill") or {}
    fill_outcome = (refresh_fill.get("outcome")
                    if isinstance(refresh_fill.get("outcome"), Mapping) else {})
    stop_reason = state.get("stop_reason")
    if not stop_reason:
        gaps = state.get("input_gaps") or []
        stop_reason = ("input_gap:{0}".format(",".join(gaps)) if gaps
                       else "completed_proposal_budget")
    # P7b：补根步骤已给出明确停因（含"预算不足/不可复现 → 保原席"）时以它为准；
    # 否则保留旧口径（停在补根态且未调度 = refresh_pending_old_seats_kept）。
    if (state.get("archive", {}).get("refresh_status") == "pending_partial"
            and not fill_outcome.get("stop_reason")):
        stop_reason = "refresh_pending_old_seats_kept"
    # —— A4：**先计入本次终态，再生成 next package** ——
    # 先落本次提案的不可变事件（含 parent/channel/family/算子/终态/失败标记），
    # 再由同一事件序列生成下一步计划；否则报告会比实际计划少算一个提案
    # （复审 R6 实测：iter-04 声明下一步 M1，iter-05 实际跑 I1）。
    state["stop_reason"] = stop_reason
    av_state_history_append(state, "ITERATION_COMPLETE", stop_reason)
    av_proposal_event_record(run_root, state, status="ITERATION_COMPLETE",
                             stop_reason=stop_reason)
    history = _av_plan_history(run_root)
    plan_next = archive_mod.next_generation_plan(archive, history)
    report = {
        "schema": AV_BATCH_REPORT_SCHEMA,
        "run_id": state["run_id"], "iteration_no": state["iteration_no"],
        "completion_status": state["status"],
        "stop_reason": stop_reason,
        "remaining_budget": {
            account: (ledger.remaining(account)
                      if ledger.authorized_total(account) is not None else None)
            for account in AV_LEDGER_ACCOUNTS},
        "spent_budget": ledger.account_summary(),
        "evidence_refs": {
            "state": str(iter_dir / "state.json"),
            "generation": str(iter_dir / "generation"),
            "admission": str(iter_dir / "admission" / "admission.json"),
            "conditional": str(iter_dir / "conditional" / "evaluation.json"),
            "natural": state.get("natural", {}).get("panel_path"),
            "statistics": state.get("summary", {}).get("statistics_path"),
            "feedback": state.get("summary", {}).get("feedback_path"),
            "archive": str(Path(run_root) / "archive" / "av-archive.json"),
            "transactions": str(iter_dir / "transactions"),
        },
        "failures_denominator": {
            "generation_rejected": 1 if state.get("rejection") else 0,
            "duplicates": 1 if (state.get("behavior") or {}).get(
                "source_duplicate_in_archive") else 0,
            "input_gaps": list(state.get("input_gaps") or []),
        },
        "archive_diff": {
            "distinct_candidates": archive.get("distinct_candidates"),
            "slots": archive.get("slots"),
        },
        # A4：提案事件序列（本次已在上面入账）——计划与报告同源可核。
        "proposal_events": {
            "path": str(av_proposal_event_path(run_root)),
            "history_count": len(history),
            "this_proposal_no": history[-1]["proposal_no"] if history else None,
            "next_proposal_no": plan_next.get("proposal_no"),
            "failed_so_far": sum(1 for row in history if row.get("failed")),
            "duplicates_so_far": sum(1 for row in history if row.get("duplicate")),
        },
        "next_task_package": {
            "proposal_no": plan_next.get("proposal_no"),
            "operator": plan_next.get("operator"),
            "parent_candidate_id": plan_next.get("parent_candidate_id"),
            "channel": plan_next.get("channel"),
            "family": plan_next.get("family"),
            "note": "唯一允许的下一步：按 next_generation_plan 调度开下一迭代；"
                    "REFRESH_PENDING 时先补齐刷新根再重排",
        },
    }
    state["batch_report"] = str(iter_dir / "batch-report.json")
    av_atomic_write_json(iter_dir / "batch-report.json", report)
    _av_tx_write(iter_dir, "batch_end", {
        "schema": "sitin-av-tx-batch-end/1", "run_id": state["run_id"],
        "stop_reason": stop_reason,
        "spent": ledger.account_summary(),
        "report_path": str(iter_dir / "batch-report.json"),
    })
    return {"advanced": "ITERATION_COMPLETE", "report": report}


# ------------------------------------------------ 跨迭代档案链发现（R6 修复）
#
# 缺口（实测）：每个 `evolve-action-value --out iter-N` 是**独立运行目录**，
# 前序迭代提交的档案落在 <iter-N>/archive/av-archive.json，而开新迭代时只读
# 本目录 → 恒判"档案空"→ 恒 I1、无父代（R6 r6-trial-runs/rep1/iter-01..04 实测）。
# 本节把"档案链"显式化成可发现、可记账的一层：调度输入（档案 + 提案历史 +
# M1 父代产物）都沿 `--out` 的**兄弟 iter-* 运行目录**发现，取最新一份；
# 显式 --archive 优先；都没有才回退空档案（I1）。本层只做选择与记账，
# **不改 sitin_archive 的算子/席位语义**（next_generation_plan 纯函数照旧）。

#: 档案步已完成的状态：该运行目录的档案产物可作下一迭代的调度输入。
AV_ARCHIVE_READY_STATUSES: Tuple[str, ...] = (
    "REFRESH_PENDING", "ARCHIVE_COMMITTED", "ITERATION_COMPLETE")
#: 档案落盘文件名（编排状态机 av-archive.json；单文件/mock 演示 archive.json）。
AV_ARCHIVE_FILENAMES: Tuple[str, ...] = ("av-archive.json", "archive.json")
#: 提案事件 schema 与账本文件名（A4：计划与报告的唯一来源；不可变追加）。
AV_PROPOSAL_EVENT_SCHEMA = "sitin-av-proposal-event/1"
AV_PROPOSAL_EVENTS_FILENAME = "proposal-events.jsonl"


def _av_chain_run_roots(run_root: Path) -> List[Path]:
    """迭代目录链上的运行目录：本目录优先，其后是父目录下按名**倒序**的兄弟 iter-*。

    "链"=同一批次里连续 `evolve --out iter-NN` 的运行目录（各自一本账、一份
    档案）。本目录排第一是为了"本目录档案优先"的确定性；兄弟按名倒序是为了
    父代/产物查找时**新迭代目录优先**。
    """

    run_root = Path(run_root)
    roots = [run_root]
    parent = run_root.parent
    if parent.is_dir():
        siblings = [item for item in sorted(parent.glob("iter-*"), reverse=True)
                    if item.is_dir() and item.resolve() != run_root.resolve()]
        roots.extend(siblings)
    return roots


def _av_iteration_dirs_in(run_root: Path) -> List[Path]:
    iterations = Path(run_root) / "iterations"
    return sorted(iterations.glob("iter-*")) if iterations.is_dir() else []


def _av_archive_candidates(root: Path) -> List[Dict[str, Any]]:
    """一个运行目录里的档案候选：常规落盘名 + 迭代状态里记录的落盘路径。

    提交标记 mark：该目录至少有一个迭代状态在档案步之后 → "committed"；
    否则 "unverified"（只有档案文件、没有可核状态，例如 mock 演示产物）。
    调用方先用 committed，再退 unverified——不因缺状态记录而静默丢链。
    """

    root = Path(root)
    states: List[Tuple[Path, Dict[str, Any]]] = []
    for iter_dir in _av_iteration_dirs_in(root):
        state_path = iter_dir / "state.json"
        if state_path.is_file():
            states.append((iter_dir, av_state_load(state_path)))
    mark = ("committed" if any(state.get("status") in AV_ARCHIVE_READY_STATUSES
                              for _, state in states) else "unverified")
    paths: List[Path] = []
    for name in AV_ARCHIVE_FILENAMES:
        paths.append(root / "archive" / name)
        paths.append(root / name)
    for iter_dir, state in states:
        for name in AV_ARCHIVE_FILENAMES:
            paths.append(iter_dir / name)
        # 等价落盘：迭代状态里记录的档案路径（若提交写的是 per-iteration 路径，
        # 发现逻辑照样覆盖它）。
        recorded = (state.get("archive") or {}).get("archive_path")
        if recorded:
            paths.append(Path(recorded))
    found: List[Dict[str, Any]] = []
    seen = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            found.append({"path": path, "mark": mark, "root": str(root)})
    return found


def _av_mtime_seconds(path: Path) -> float:
    """档案文件 mtime（Unix 秒）；取不到返回 -1（文件在扫描后消失也不崩选择）。"""

    try:
        return Path(path).stat().st_mtime
    except OSError:
        return -1.0


def _av_mtime_utc(path: Path) -> Optional[str]:
    """档案文件 mtime 的 UTC 口径（墙上时钟，ISO 8601 秒级）；取不到返回 None。"""

    stamp = _av_mtime_seconds(path)
    if stamp < 0:
        return None
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _av_newest_archive(candidates: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """取 mtime 最新的一份（并列时按路径字典序，保证同输入同选择）。"""

    return max(candidates, key=lambda item: (_av_mtime_seconds(item["path"]),
                                             str(item["path"])))


# ===========================================================================
# 跨目录连续恢复 · 调度输入档案的**内容身份绑定**（R9 裁定 §7 末段）
#
# 裁定原文：跨目录连续恢复前必须补齐已登记的 archive_in 内容身份——开轮固化档案、
# 家族 epoch、根用途清单，**读取固定快照**；当前源码在提交时再次读取档案路径，
# 第一方源码身份完整并不自动保证输入数据相同。
#
# 缺陷复述：开轮把 archive_in 的**路径**记进 state.plan，随后提交/补根时按路径**再读**
# 一次——同一路径被改写（换内容不改路径）时，运行身份摘要逐字不变（源码没变），
# 输入数据却已经不是那一份，恢复就此建立在另一份输入上。
#
# 修法：
#   ① 开轮把输入档案本体、家族 epoch 表、根用途清单的**内容摘要 + 固定快照副本**
#      固化到迭代目录 inputs/ 下，并登记进 state.plan.archive_in.content_identity；
#   ② 此后一切读取走**固定快照**（不再按路径重读）；
#   ③ 跨目录（输入目录不是本运行目录的 archive/）的登记项在恢复/提交前**核对现场
#      内容**：内容变了即**拒绝恢复**（ArchiveInputDrift / 具名停因），不静默改用新内容。
#      本运行目录自己的档案不做漂移拒绝（本迭代提交会合法改写它，它是增量提交基数），
#      但仍固化内容身份供事后核对——两种情形在产物里如实分列。
# ===========================================================================

#: 输入内容身份 schema（开轮固化；字段固定便于逐项复核）。
AV_ARCHIVE_INPUT_IDENTITY_SCHEMA = "sitin-av-archive-input-identity/1"
#: 输入固定快照目录（迭代目录下）。
AV_ARCHIVE_INPUT_DIR = "inputs"
#: 输入内容漂移的具名停因（拒绝恢复）。
AV_ARCHIVE_INPUT_DRIFT_STOP_REASON = "archive_in_content_drift_recovery_refused"
#: —— P16-S1 具名停因：冻结/身份/快照三条各自可分（不合成一个笼统"输入有问题"）——
#: 必需输入**无法冻结**（快照或身份件写不进去）：开轮即具名停止。
AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON = "archive_in_content_identity_freeze_failed"
#: 本次状态**没有登记内容身份**（旧状态/未接线/被跳过）：拒绝恢复并要求显式新开评价。
AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON = \
    "archive_in_content_identity_missing_recovery_refused"
#: 已登记**固定快照**缺失：拒绝恢复（不能用"原文件未变"证明"快照未变"）。
AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON = "archive_in_frozen_snapshot_missing"
#: 已登记固定快照的**字节**与开轮登记不符：拒绝恢复（消费前必须核验实际读取的字节）。
AV_ARCHIVE_INPUT_SNAPSHOT_MISMATCH_STOP_REASON = "archive_in_frozen_snapshot_sha256_mismatch"
#: **明确兼容**的旧夹具开关（必须写在 state.plan.archive_in 里，显式、可审计）：
#: 只有带本标记的状态才允许"未登记内容身份"按旧夹具放行；缺省一律失败关闭。
AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY = "legacy_compat_unregistered"
#: 空档案新运行的分支记号（archive_in.source 的值；无输入数据可核，属合法新运行）。
AV_ARCHIVE_INPUT_EMPTY_SOURCE = "empty"


class ArchiveInputFreezeFailed(RuntimeError):
    """必需输入**无法冻结**（快照/身份件写不进去）：开轮即具名停止，不得继续执行。"""
#: 纳入内容身份的输入件（种类 → 文件名；都是"跨目录继承"的那几份）。
AV_ARCHIVE_INPUT_FILES: Tuple[Tuple[str, str], ...] = (
    ("family_epochs", "family-epochs.json"),
    ("root_purpose_list", "family-roots.json"),
    ("normal_epoch", "normal-epoch.json"),
    ("normal_roots", "normal-roots.json"),
)


class ArchiveInputDrift(RuntimeError):
    """调度输入档案的内容与开轮登记的身份不符：**拒绝**按新内容继续（fail-closed）。"""


def _av_freeze_artifact(kind: str, path: Path, snapshot_dir: Path, *,
                        enforced: bool, note: str) -> Dict[str, Any]:
    """固化一个输入件：内容摘要 + 固定快照副本（读取一律走快照）。

    P16-S1：快照写入**不许吞异常**（写不进去即"必需输入无法冻结"）；写完当场回读
    核对字节摘要——登记进身份的 snapshot_sha256 必须是**实际落盘那一份**的摘要，
    否则后面的"快照字节核验"会以错为准。
    """

    data = Path(path).read_bytes()
    snapshot = Path(snapshot_dir) / "{0}.snapshot".format(kind)
    try:
        av_atomic_write_bytes(snapshot, data)
    except OSError as error:
        raise ArchiveInputFreezeFailed(
            "必需输入的固定快照写不进去（{0}：{1}）：开轮即具名停止（{2}）".format(
                kind, error, AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON)) from error
    try:
        written = Path(snapshot).read_bytes()
    except OSError as error:
        raise ArchiveInputFreezeFailed(
            "固定快照写完却读不回来（{0}：{1}）：无法证明快照与登记一致，具名停止"
            "（{2}）".format(kind, error, AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON)
        ) from error
    digest = hashlib.sha256(data).hexdigest()
    if hashlib.sha256(written).hexdigest() != digest:
        raise ArchiveInputFreezeFailed(
            "固定快照写完的字节与输入不一致（{0}）：具名停止（{1}）".format(
                kind, AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON))
    return {"kind": kind, "path": str(Path(path)), "bytes": len(data),
            "content_sha256": digest,
            "snapshot": str(snapshot),
            "snapshot_sha256": digest,
            "enforced_drift_refusal": bool(enforced), "note": note}


def av_archive_input_freeze(state: Dict[str, Any], run_root: Path) -> Optional[Dict[str, Any]]:
    """开轮**固化**调度输入的内容身份与固定快照（跨目录连续恢复的前置条件）。

    P16-S1 的三条分支（不再把未登记状态普遍放行）：
      - 有输入档案路径且文件在 → 固化内容身份 + 固定快照（写不进去即
        ArchiveInputFreezeFailed，由开轮入口具名停止）；
      - 空档案新运行（source=empty，无输入档案）→ 明确记为 empty_archive 分支
        （没有跨目录输入数据可核，属合法新运行）；
      - 既无路径也不是空档案（旧调用路径/未接线）→ 记为 identity_missing，
        恢复入口据此**拒绝**（除非状态里显式写了兼容标记 legacy_compat_unregistered）。
    """

    plan = state.get("plan")
    if not isinstance(plan, MutableMapping):
        return None
    record = plan.get("archive_in")
    if not isinstance(record, Mapping):
        return None
    existing = record.get("content_identity")
    if isinstance(existing, Mapping) and existing.get("schema") == \
            AV_ARCHIVE_INPUT_IDENTITY_SCHEMA:
        return dict(existing)                      # 幂等：重入不重写（同一份身份）
    run_root = Path(run_root)
    iter_dir = Path(str(state.get("iter_dir") or run_root))
    snapshot_dir = iter_dir / AV_ARCHIVE_INPUT_DIR
    local_dir = (run_root / "archive").resolve()
    artifacts: List[Dict[str, Any]] = []
    path_text = record.get("path")
    source_text = str(record.get("source") or "")
    branch = "frozen"
    branch_note = ("开轮固化档案、家族 epoch、根用途清单的内容身份并留固定快照；"
                   "此后读取走快照，跨目录登记项在恢复前核对现场内容（漂移即拒绝恢复），"
                   "且消费前核对**实际读取的快照字节**")
    if path_text:
        archive_path = Path(str(path_text))
        if archive_path.is_file():
            input_dir = archive_path.parent
            cross = input_dir.resolve() != local_dir
            artifacts.append(_av_freeze_artifact(
                "archive", archive_path, snapshot_dir, enforced=cross,
                note=("跨目录输入：内容变了即拒绝恢复" if cross else
                      "本运行目录自己的档案（增量提交基数，本迭代提交会合法改写）："
                      "只固化内容身份供核对，不做漂移拒绝")))
            for kind, name in AV_ARCHIVE_INPUT_FILES:
                candidate = input_dir / name
                if candidate.is_file():
                    artifacts.append(_av_freeze_artifact(
                        kind, candidate, snapshot_dir, enforced=cross,
                        note=("跨目录输入（{0}）：内容变了即拒绝恢复".format(
                            "家族 epoch" if kind == "family_epochs" else
                            "根用途清单" if kind == "root_purpose_list" else kind)
                            if cross else
                            "本运行目录自己的产物：只固化内容身份供核对")))
        else:
            # 记了路径却读不到：不是"没有输入"，是**必需输入无法冻结**。
            raise ArchiveInputFreezeFailed(
                "调度输入档案读不到（{0}）：必需输入无法冻结，开轮即具名停止（{1}）".format(
                    path_text, AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON))
    elif source_text == AV_ARCHIVE_INPUT_EMPTY_SOURCE:
        branch = "empty_archive"
        branch_note = ("空档案新运行（没有跨目录输入档案）：无输入数据可核，按"
                       "「空档案」分支显式放行——不是把未登记状态普遍放行")
    else:
        branch = "identity_missing"
        branch_note = ("本次没有可固化的调度输入档案（source={0!r}）：记 identity_missing，"
                       "恢复入口拒绝继续（要用旧夹具请显式写 {1}=true）".format(
                           source_text, AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY))
    identity = {
        "schema": AV_ARCHIVE_INPUT_IDENTITY_SCHEMA,
        "source": record.get("source"), "path": path_text,
        "branch": branch,
        "frozen_at_utc": utc_now(), "snapshot_dir": str(snapshot_dir),
        "artifacts": artifacts,
        "enforced_kinds": [item["kind"] for item in artifacts
                           if item.get("enforced_drift_refusal")],
        "note": branch_note,
    }
    updated = dict(record)
    updated["content_identity"] = identity
    plan["archive_in"] = updated
    try:
        av_atomic_write_json(iter_dir / "archive-input-identity.json", identity)
    except OSError as error:
        # 必需冻结件写不进去 ⇒ 具名停止（不"当作没登记"继续跑）。
        raise ArchiveInputFreezeFailed(
            "输入内容身份件写不进去（{0}）：必需冻结件写入失败即停止（{1}）".format(
                error, AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON)) from error
    return identity


def _av_archive_input_identity(state: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """在案的内容身份块（未登记返回 None：调用方据此按分支**拒绝**，不放行）。"""

    identity = (((state.get("plan") or {}).get("archive_in") or {})
                .get("content_identity"))
    return identity if isinstance(identity, Mapping) else None


def _av_archive_input_verify_result(state: Mapping[str, Any], *,
                                    ok: bool, status: str,
                                    problems: Sequence[Mapping[str, Any]] = (),
                                    stop_reason: Optional[str] = None,
                                    identity: Optional[Mapping[str, Any]] = None,
                                    note: str = "") -> Dict[str, Any]:
    """统一的核验结果形状（ok / status / stop_reason / problems 四处口径一致）。"""

    return {"schema": AV_ARCHIVE_INPUT_IDENTITY_SCHEMA,
            "ok": bool(ok), "status": str(status),
            "stop_reason": (None if ok else (stop_reason
                                             or AV_ARCHIVE_INPUT_DRIFT_STOP_REASON)),
            "path": (identity or {}).get("path"),
            "source": (identity or {}).get("source"),
            "branch": (identity or {}).get("branch"),
            "artifacts": list((identity or {}).get("artifacts") or ()),
            "enforced_kinds": list((identity or {}).get("enforced_kinds") or ()),
            "problems": [dict(item) for item in problems],
            "checked_at_utc": utc_now(), "note": note}


def av_archive_input_verify(state: Mapping[str, Any], *,
                            allow_unregistered: bool = False) -> Dict[str, Any]:
    """核对已登记的跨目录输入件是否仍与开轮一致：**四类失败各自具名**、缺身份即拒绝。

    P16-S1：
      - 已登记身份 → 逐件核对 **①现场原文件内容**（仅 enforced 件）与
        **②固定快照的存在性与字节摘要**（所有件）——"原文件未变"证明不了"快照未变"，
        消费前必须核验**实际会被读取的那份字节**；
      - 身份缺失（未登记）→ 默认 **ok=False**（停因 identity_missing，要求显式新开
        评价）；只有两种**显式分支**放行：空档案新运行（source=empty）与状态里显式
        写了兼容标记 legacy_compat_unregistered 的旧夹具（allow_unregistered=True 亦
        为显式调用方选择，供离线复算/旧夹具，不在生产恢复路径上）。
    """

    identity = _av_archive_input_identity(state)
    if identity is None:
        record = ((state.get("plan") or {}).get("archive_in") or {})
        record = record if isinstance(record, Mapping) else {}
        if record.get(AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY) is True or allow_unregistered:
            return _av_archive_input_verify_result(
                state, ok=True, status="unregistered_explicit_legacy_compat",
                identity=record,
                note=("显式兼容分支（{0}=true 或调用方 allow_unregistered）：本次按旧夹具"
                      "放行；生产恢复路径不默认走这条").format(
                          AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY))
        if (str(record.get("source") or "") == AV_ARCHIVE_INPUT_EMPTY_SOURCE
                and record.get("path") in (None, "")):
            return _av_archive_input_verify_result(
                state, ok=True, status="empty_archive_new_run", identity=record,
                note=("空档案新运行（无跨目录输入档案）：没有可核的输入数据，属合法"
                      "新运行——不是把未登记状态普遍放行"))
        return _av_archive_input_verify_result(
            state, ok=False, status="identity_missing",
            stop_reason=AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON,
            problems=[{
                "kind": "archive_input_identity", "path": record.get("path"),
                "reason": ("本次状态没有登记调度输入内容身份（source={0!r}）：无法证明"
                           "恢复用的是开轮那一份输入——**拒绝恢复**并要求显式新开评价"
                           "（{1}）").format(record.get("source"),
                                            AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON)}],
            note="身份缺失即拒绝（fail-closed）：不以 unregistered 普遍放行")
    branch = str(identity.get("branch") or "")
    if branch == "identity_missing":
        record = ((state.get("plan") or {}).get("archive_in") or {})
        record = record if isinstance(record, Mapping) else {}
        if record.get(AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY) is True or allow_unregistered:
            return _av_archive_input_verify_result(
                state, ok=True, status="unregistered_explicit_legacy_compat",
                identity=identity,
                note=("显式兼容分支（{0}=true 或调用方 allow_unregistered）：本次按旧夹具"
                      "放行；生产恢复路径不默认走这条").format(
                          AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY))
        return _av_archive_input_verify_result(
            state, ok=False, status="identity_missing",
            stop_reason=AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON, identity=identity,
            problems=[{
                "kind": "archive_input_identity", "path": identity.get("path"),
                "reason": ("开轮登记的是 identity_missing（没有可固化的调度输入档案）："
                           "拒绝恢复（{0}）").format(
                               AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON)}],
            note="开轮已判身份缺失：恢复入口一致拒绝")
    if str(identity.get("branch") or "") == "empty_archive":
        return _av_archive_input_verify_result(
            state, ok=True, status="empty_archive_new_run", identity=identity,
            note="空档案新运行：无输入数据可核（分支显式，不掩盖身份缺失）")
    drift: List[Dict[str, Any]] = []
    snapshot_missing: List[Dict[str, Any]] = []
    snapshot_mismatch: List[Dict[str, Any]] = []
    for entry in identity.get("artifacts") or ():
        kind = entry.get("kind")
        if entry.get("enforced_drift_refusal"):
            path = Path(str(entry.get("path")))
            try:
                current = _av_file_digest(path)
            except OSError:
                current = None
            if str(current or "") != str(entry.get("content_sha256") or ""):
                drift.append({
                    "kind": kind, "path": str(path),
                    "recorded_sha256": entry.get("content_sha256"),
                    "current_sha256": current,
                    "reason": ("调度输入内容已变（换内容不改路径）：开轮登记的是另一份"
                               "数据，拒绝恢复——不得按新内容继续，也不得静默改写身份")})
        snapshot_text = entry.get("snapshot")
        if not snapshot_text:
            snapshot_missing.append({
                "kind": kind, "path": entry.get("path"),
                "reason": "身份里没有固定快照路径：无法证明消费的是开轮那一份字节"})
            continue
        snapshot_path = Path(str(snapshot_text))
        try:
            actual = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        except OSError:
            snapshot_missing.append({
                "kind": kind, "path": str(snapshot_path),
                "recorded_sha256": entry.get("snapshot_sha256"),
                "reason": ("固定快照不在/读不到：开轮登记的快照已被删除或不可读，"
                           "拒绝恢复（{0}）").format(
                               AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON)})
            continue
        if str(actual) != str(entry.get("snapshot_sha256") or ""):
            snapshot_mismatch.append({
                "kind": kind, "path": str(snapshot_path),
                "recorded_sha256": entry.get("snapshot_sha256"),
                "current_sha256": actual,
                "reason": ("固定快照的字节与开轮登记不符：消费的会是另一份内容，"
                           "拒绝恢复（{0}）").format(
                               AV_ARCHIVE_INPUT_SNAPSHOT_MISMATCH_STOP_REASON)})
    problems = drift + snapshot_missing + snapshot_mismatch
    if drift:
        return _av_archive_input_verify_result(
            state, ok=False, status="drift",
            stop_reason=AV_ARCHIVE_INPUT_DRIFT_STOP_REASON, identity=identity,
            problems=problems, note="调度输入漂移：拒绝恢复")
    if snapshot_missing:
        return _av_archive_input_verify_result(
            state, ok=False, status="snapshot_missing",
            stop_reason=AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON, identity=identity,
            problems=problems, note="固定快照缺失：拒绝恢复")
    if snapshot_mismatch:
        return _av_archive_input_verify_result(
            state, ok=False, status="snapshot_mismatch",
            stop_reason=AV_ARCHIVE_INPUT_SNAPSHOT_MISMATCH_STOP_REASON, identity=identity,
            problems=problems, note="固定快照字节不符：拒绝恢复")
    return _av_archive_input_verify_result(
        state, ok=True, status="matched", identity=identity,
        note="现场内容与固定快照字节均与开轮登记一致")


def _av_frozen_input_bytes(state: Mapping[str, Any], path: Path) -> Optional[bytes]:
    """读一个已登记输入件：**固定快照**优先；跨目录登记项现场内容不符即拒绝。

    返回 None 表示"该路径不在本迭代的登记里"——调用方按原行为直接读路径（旧状态、
    夹具路径、本运行目录自己新生成的产物都走这条路）。
    """

    identity = _av_archive_input_identity(state)
    if identity is None:
        return None
    key = str(Path(path))
    for entry in identity.get("artifacts") or ():
        if str(entry.get("path")) != key:
            continue
        if entry.get("enforced_drift_refusal"):
            try:
                current = _av_file_digest(Path(key))
            except OSError:
                current = None
            if str(current or "") != str(entry.get("content_sha256") or ""):
                raise ArchiveInputDrift(
                    "调度输入 {0}（{1}）内容已变：开轮登记 {2}，现场 {3}——"
                    "拒绝恢复（{4}）".format(entry.get("kind"), key,
                                            entry.get("content_sha256"), current,
                                            AV_ARCHIVE_INPUT_DRIFT_STOP_REASON))
        snapshot = entry.get("snapshot")
        if not snapshot:
            # 身份里没有快照路径：不能退回按路径重读（那正是"换内容不改路径"的缺口）。
            raise ArchiveInputDrift(
                "调度输入 {0}（{1}）没有固定快照：拒绝恢复（{2}）".format(
                    entry.get("kind"), key, AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON))
        snapshot_path = Path(str(snapshot))
        try:
            data = snapshot_path.read_bytes()
        except OSError as error:
            raise ArchiveInputDrift(
                "调度输入 {0}（{1}）的固定快照读不到（{2}：{3}）：拒绝恢复（{4}）".format(
                    entry.get("kind"), key, snapshot_path, error,
                    AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON)) from error
        # **核验实际消费的那份字节**：登记摘要与现场字节不符即拒绝——"原文件未变"
        # 证明不了"快照未变"（P16-S1）。
        actual = hashlib.sha256(data).hexdigest()
        recorded = str(entry.get("snapshot_sha256") or "")
        if not recorded or actual != recorded:
            raise ArchiveInputDrift(
                "调度输入 {0}（{1}）的固定快照字节与开轮登记不符：登记 {2}，现场 {3}——"
                "拒绝按这份快照恢复（{4}）".format(
                    entry.get("kind"), key, recorded, actual,
                    AV_ARCHIVE_INPUT_SNAPSHOT_MISMATCH_STOP_REASON))
        return data
    return None


def av_discover_archive(out_dir: Path, *,
                        explicit: Optional[Path] = None,
                        ) -> Tuple[Optional[Path], Dict[str, Any]]:
    """定位本迭代的**调度输入档案**：显式 > 本目录 > 迭代目录链最新 > 空档案。

    - explicit 给定：必须是**存在的文件**；不存在返回 source=explicit_missing，
      调用方拒绝开轮（fail-closed，不静默回退自动发现或空档案）；
    - 否则本运行目录 `archive/{av-archive.json,archive.json}` 等优先（同一
      --out 内连续迭代的原行为不变）；
    - 否则扫 `--out` **父目录**下兄弟 iter-* 运行目录的 ARCHIVE_COMMITTED 产物
      （archive/av-archive.json、archive.json、迭代状态里记录的落盘路径），
      取 mtime 最新的一份作为调度输入；
    - 都没有 → (None, source=empty)：调用方回退空档案（next_generation_plan
      对空档案/无席位档案返回 I1）。

    返回 (路径, 发现记录)；发现记录含 source/mtime_utc/run_root/candidates/
    chain_roots，随 state.plan.archive_in 落盘（"档案从哪来"可事后核对）。
    """

    out_dir = Path(out_dir)
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            return None, {"source": "explicit_missing", "path": str(path),
                          "mtime_utc": None, "run_root": None, "candidates": 0,
                          "reason": "显式指定的共享档案不存在"}
        return path, {"source": "explicit", "path": str(path),
                      "mtime_utc": _av_mtime_utc(path), "run_root": None,
                      "candidates": 1}
    roots = _av_chain_run_roots(out_dir)
    chain_roots = [str(root) for root in roots]
    local = _av_archive_candidates(roots[0])
    if local:
        best = _av_newest_archive(local)
        return best["path"], {"source": "local", "path": str(best["path"]),
                              "mtime_utc": _av_mtime_utc(best["path"]),
                              "run_root": best["root"],
                              "candidates": len(local),
                              "chain_roots": chain_roots}
    chain = [item for root in roots[1:] for item in _av_archive_candidates(root)]
    for mark in ("committed", "unverified"):
        tier = [item for item in chain if item["mark"] == mark]
        if tier:
            best = _av_newest_archive(tier)
            return best["path"], {"source": "chain_" + mark,
                                  "path": str(best["path"]),
                                  "mtime_utc": _av_mtime_utc(best["path"]),
                                  "run_root": best["root"],
                                  "candidates": len(chain),
                                  "chain_roots": chain_roots}
    return None, {"source": "empty", "path": None, "mtime_utc": None,
                  "run_root": None, "candidates": 0,
                  "chain_roots": chain_roots}


def _av_archive_in_record(path: Optional[Path], discovery: Mapping[str, Any],
                          archive: Mapping[str, Any],
                          history: Sequence[Mapping[str, Any]],
                          plan: Mapping[str, Any]) -> Dict[str, Any]:
    """调度输入档案的记账（state.plan.archive_in 与迭代结果共用同一形状）。

    path/source/mtime_utc 说明**档案从哪来**（显式/本目录/迭代目录链/空）；
    entries/seated_slots 是**生成本计划所用档案**的内容——evolve 状态机里就是
    这份调度输入档案，mock 演示路径里是本步刚更新过的档案（含本迭代新条目）；
    planned_operator 是 C2 调度的结论，是否真的采用另记 applied_operator
    （父代产物不可绑定时回退 I1，不凭空造父代）。
    """

    slots = archive.get("slots") or {}
    return {
        "path": str(path) if path is not None else None,
        "source": discovery.get("source"),
        "mtime_utc": discovery.get("mtime_utc"),
        "run_root": discovery.get("run_root"),
        "entries": len(archive.get("entries") or {}),
        "seated_slots": {channel: len(ids or [])
                         for channel, ids in sorted(slots.items())},
        "candidates_seen": discovery.get("candidates"),
        "chain_roots": discovery.get("chain_roots"),
        "history_count": len(history),
        "proposal_no": plan.get("proposal_no"),
        "planned_operator": plan.get("operator"),
        "planned_parent_candidate_id": plan.get("parent_candidate_id"),
        # A4：计划里的通道/家族一并记账——提案事件的 parent/channel/family 由此而来，
        # 缺它就会让"父代最少使用"与专长轮转静默失效。
        "planned_channel": plan.get("channel"),
        "planned_family": plan.get("family"),
    }


def _av_previous_archive(state: Mapping[str, Any],
                         run_root: Path) -> Dict[str, Any]:
    """本迭代提交前的在案档案（增量提交的基数）。

    顺序：本运行目录的档案 → 开轮时记下的调度输入档案（state.plan.archive_in）
    → 迭代目录链上最新的一份 → 空档案。跨 `--out iter-NN` 的增量提交靠后两级
    成立：新迭代目录**没有**自己的档案时，以前序提交的档案为基数合并，不把链
    截断成单候选；同时与开轮时的调度输入保持同一份（不在中途偷换比较基准）。
    """

    local = Path(run_root) / "archive" / "av-archive.json"
    if local.is_file():
        return json.loads(local.read_text(encoding="utf-8"))
    recorded = ((state.get("plan") or {}).get("archive_in") or {}).get("path")
    if recorded and Path(recorded).is_file():
        # 内容身份绑定：已登记的输入走**固定快照**；跨目录登记项内容变了直接拒绝
        # （不按新内容继续——"换内容不改路径"必须被发现）。
        frozen = _av_frozen_input_bytes(state, Path(recorded))
        if frozen is not None:
            return json.loads(frozen.decode("utf-8"))
        return json.loads(Path(recorded).read_text(encoding="utf-8"))
    discovered, _discovery = av_discover_archive(Path(run_root))
    if discovered is not None:
        return json.loads(discovered.read_text(encoding="utf-8"))
    return {"entries": {}, "slots": {}}


def av_proposal_event_path(run_root: Path) -> Path:
    """提案事件账本路径（每个运行目录一本；沿运行链合并读取）。"""

    return Path(run_root) / "archive" / AV_PROPOSAL_EVENTS_FILENAME


def _av_proposal_events(run_root: Path) -> List[Dict[str, Any]]:
    """读取本运行目录的提案事件账本（JSONL；坏行跳过但不静默改语义）。"""

    path = av_proposal_event_path(run_root)
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def av_proposal_event_append(run_root: Path, event: Mapping[str, Any]) -> Dict[str, Any]:
    """**不可变**追加一条提案事件；同一迭代已有事件则原样返回旧事件（不改写）。

    事件是计划与报告的唯一来源（A4）：同一迭代被重复记录（例如批末与终态两处）
    时必须返回同一条，不产生两条口径不同的历史。
    """

    path = av_proposal_event_path(run_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("schema", AV_PROPOSAL_EVENT_SCHEMA)
    payload.setdefault("recorded_at_utc", utc_now())
    key = _av_proposal_event_key(payload)
    for row in _av_proposal_events(run_root):
        if _av_proposal_event_key(row) == key:
            return row
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(payload) + "\n")
    return payload


def _av_proposal_identity(row: Mapping[str, Any]) -> Optional[Tuple[str, ...]]:
    """提案**显式身份**：(run_id, iteration_no) → (run_id, 记录号) → 目录 → 记录号。

    P18 判定（run7 副本根实测）：旧实现的事件行用 Path(iter_dir).resolve() 作键——
    运行根被复制/搬运后事件行里的 iter_dir **仍指原路径**，而状态投影行用**当前**路径，
    同一提案因此被登记两次（2 提案变 4 条 ⇒ proposal_no = len+1 = 5 ⇒ 算子从 M1 误判为
    I1）。去重键必须用**提案身份**，不是路径。

    口径与 sitin_archive._proposal_identity **逐条一致**（上游折叠 / 下游检查必须同源，
    漂移会让两套判据互相矛盾）；两处都只用产物里显式写出的身份字段，没有身份字段的旧
    历史返回 None（调用方按"不可判重复"处理，不猜）。
    """

    def _positive_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    run_id = row.get("run_id")
    run_id = run_id.strip() if isinstance(run_id, str) else ""
    # 只认 recorded_proposal_no（与 sitin_archive._proposal_identity 同口径）：
    # 事件行自带的 proposal_no 不参与身份——两侧口径不同步会让折叠与下游检查互相矛盾。
    recorded = row.get("recorded_proposal_no")
    iteration_no = row.get("iteration_no")
    if run_id and _positive_int(iteration_no):
        return ("iteration", run_id, str(iteration_no))
    if run_id and _positive_int(recorded):
        return ("proposal", run_id, str(recorded))
    iter_dir = row.get("iter_dir")
    if isinstance(iter_dir, str) and iter_dir.strip():
        return ("iter_dir", iter_dir.strip())
    if _positive_int(recorded):
        return ("proposal_no", str(recorded))
    return None


def _av_proposal_event_key(event: Mapping[str, Any]) -> Tuple[str, ...]:
    """事件身份键 = **提案身份**（同一提案只允许一条事件，与路径无关）。

    没有身份字段的旧事件退回目录串（**不 resolve**：搬运后 resolve 会指向原路径，
    那正是重复登记的来源）。
    """

    identity = _av_proposal_identity(event)
    if identity is not None:
        return identity
    return ("unidentified", str(event.get("iter_dir") or ""),
            str(event.get("run_id") or ""))


def _av_proposal_event_for(state: Mapping[str, Any], *, status: Optional[str] = None,
                           stop_reason: Optional[str] = None) -> Dict[str, Any]:
    """由迭代状态构造**完整提案事件**（含 parent/channel/family/算子/终态/失败标记）。

    算子口径：applied_operator = 真正执行的算子（计划 M1 但父代产物绑不上时回退
    I1 已经被记录在 archive_in.applied_operator）；父代/通道/家族只在**真正执行
    M1** 时计入使用计数——回退的提案仍占提案额度，但不冒充某通道的父代使用。
    """

    plan = state.get("plan") or {}
    archive_in = plan.get("archive_in") or {}
    applied = str(archive_in.get("applied_operator") or plan.get("operator")
                  or "i1").upper()
    terminal = str(status or state.get("status") or "")
    failed = terminal in ("REJECTED", "BUDGET_EXHAUSTED", "EXECUTION_FAILED") or bool(
        state.get("rejection"))
    return {
        "schema": AV_PROPOSAL_EVENT_SCHEMA,
        "proposal_no": int(archive_in.get("proposal_no") or state.get("iteration_no")
                           or 0),
        "run_id": state.get("run_id"),
        "iteration_no": state.get("iteration_no"),
        "iter_dir": state.get("iter_dir"),
        "operator": applied,
        "planned_operator": str(archive_in.get("planned_operator") or applied).upper(),
        "applied_operator": applied,
        "parent_candidate_id": (archive_in.get("planned_parent_candidate_id")
                                if applied == "M1" else None),
        "planned_parent_candidate_id": archive_in.get("planned_parent_candidate_id"),
        "channel": (archive_in.get("planned_channel") if applied == "M1" else None),
        "family": (archive_in.get("planned_family") if applied == "M1" else None),
        "candidate_id": (state.get("identity") or {}).get("candidate_id"),
        "status": terminal,
        "terminal_status": terminal,
        "stop_reason": stop_reason or state.get("stop_reason"),
        "failed": failed,
        "duplicate": bool((state.get("behavior") or {}).get(
            "behavior_duplicate_in_archive")),
        "archive_in_source": archive_in.get("source"),
        # P18：事件行也要带 created_at_utc（取自迭代状态的创建时间），否则混合账本里
        # 事件行会因该字段缺失被排到投影行之前 ⇒ 位置号与记录号错位。
        "created_at_utc": (state.get("created_at_utc") or utc_now()),
        "recorded_at_utc": utc_now(),
    }


def av_proposal_event_record(run_root: Path, state: Mapping[str, Any],
                             *, status: Optional[str] = None,
                             stop_reason: Optional[str] = None) -> Dict[str, Any]:
    """落一条本迭代的提案事件（幂等：同一迭代重复调用返回同一条）。"""

    return av_proposal_event_append(
        run_root, _av_proposal_event_for(state, status=status,
                                         stop_reason=stop_reason))


def _av_proposal_record_from_state(state: Mapping[str, Any],
                                   key: str) -> Dict[str, Any]:
    """旧产物兼容投影：没有事件账本的迭代状态 → 尽力投影成同形状记录。

    只用于**既有历史**（事件账本引入之前的运行目录）；通道/家族缺字段时留 None，
    不猜——计数回退到"未归属"桶，不硬塞进某通道。
    """

    plan = state.get("plan") or {}
    archive_in = plan.get("archive_in") or {}
    applied = str(archive_in.get("applied_operator") or plan.get("operator")
                  or "i1").upper()
    status = state.get("status")
    row = _av_proposal_event_for(state, status=status)
    row.update({
        "iter_dir": key,
        "created_at_utc": state.get("created_at_utc") or "",
        "source": "state_projection",
        "channel": (archive_in.get("planned_channel") if applied == "M1" else None),
        "family": (archive_in.get("planned_family") if applied == "M1" else None),
        "parent_candidate_id": (archive_in.get("planned_parent_candidate_id")
                                if applied == "M1" else None),
    })
    return row


def _av_plan_history(run_root: Path) -> List[Dict[str, Any]]:
    """提案历史（供 next_generation_plan 的使用计数与提案号）。

    A4：以**不可变提案事件**为主（链上各运行目录的 proposal-events.jsonl）；
    事件账本引入之前的旧迭代状态补一条同形状投影。
    跨迭代链：本目录 + 父目录下兄弟 iter-* 运行目录。只计**已终态**的提案——
    失败/重复同样占提案额度，在途提案不计。

    P18 修复（run7 副本根实测）：去重键 = **提案身份**（(run_id, iteration_no) →
    (run_id, 记录号) → 目录 → 记录号），**不用 resolve 后的路径**——运行根被复制/搬运后
    事件行里的 iter_dir 仍指原路径、投影行用当前路径，同一提案会被登记两次（2 提案变
    4 条 ⇒ proposal_no 5 ⇒ 算子从 M1 误判为 I1）。折叠只在真的重复时发生，并留档在首行
    的 collapsed_duplicates。排序按 (created_at_utc, 记录号, 目录)：事件行与投影行都写
    created_at_utc，不再依赖"缺字段默认空串"把事件行排到投影行之前。
    """

    records: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    collapsed: List[Dict[str, Any]] = []
    for root in _av_chain_run_roots(run_root):
        for event in _av_proposal_events(root):
            row = dict(event, source="event")
            key = _av_proposal_event_key(row)
            if key in records:
                if str(row.get("iter_dir")) != str(records[key].get("iter_dir")):
                    collapsed.append({"identity": list(key), "kept": "event",
                                      "folded_source": "event",
                                      "iter_dir": row.get("iter_dir"),
                                      "kept_iter_dir": records[key].get("iter_dir")})
                continue
            records[key] = row
    for root in _av_chain_run_roots(run_root):
        for iter_dir in _av_iteration_dirs_in(root):
            state_path = iter_dir / "state.json"
            if not state_path.is_file():
                continue
            state = av_state_load(state_path)
            status = state.get("status")
            if not (status in AV_TERMINAL_STATES or status == "ITERATION_COMPLETE"):
                continue
            row = _av_proposal_record_from_state(state, str(iter_dir))
            key = _av_proposal_identity(row)
            if key is None:
                # 无身份字段的旧状态：退回目录串（不 resolve，避免搬运后与原路径混同）。
                key = ("iter_dir", str(iter_dir))
            if key in records:
                if str(iter_dir) != str(records[key].get("iter_dir")):
                    collapsed.append({"identity": list(key), "kept": "event",
                                      "folded_source": "state_projection",
                                      "iter_dir": str(iter_dir),
                                      "kept_iter_dir": records[key].get("iter_dir")})
                continue
            records[key] = row
    # 排序按**身份/记录号**，不依赖可能缺失的时间字段（事件行缺 created_at_utc 时会
    # 被排到投影行之前，位置号与记录号错位——P18 实测）。
    ordered = sorted(records.values(),
                     key=lambda row: (
                         str(row.get("created_at_utc") or ""),
                         str(row.get("recorded_proposal_no")
                             if row.get("recorded_proposal_no") is not None
                             else row.get("proposal_no") or ""),
                         str(row.get("iter_dir") or "")))
    history: List[Dict[str, Any]] = []
    for index, row in enumerate(ordered):
        history.append({
            "proposal_no": index + 1,
            "recorded_proposal_no": row.get("proposal_no"),
            "operator": str(row.get("operator") or "I1").upper(),
            "planned_operator": row.get("planned_operator"),
            "applied_operator": row.get("applied_operator") or row.get("operator"),
            "parent_candidate_id": row.get("parent_candidate_id"),
            "channel": row.get("channel"),
            "family": row.get("family"),
            "candidate_id": row.get("candidate_id"),
            "status": row.get("status"),
            "terminal_status": row.get("terminal_status") or row.get("status"),
            "failed": bool(row.get("failed")),
            "duplicate": bool(row.get("duplicate")),
            "iter_dir": row.get("iter_dir"),
            "run_id": row.get("run_id"),
            "created_at_utc": row.get("created_at_utc") or "",
            "source": row.get("source") or "event",
        })
    if collapsed and history:
        # 折叠留档（只在真的发生重复时出现，正常运行的行形状逐字不变）。
        history[0]["collapsed_duplicates"] = [
            dict(entry, note=("同一提案的第二条登记（路径不同源）已折叠：上游不产生重复，"
                              "核对可查这里")) for entry in collapsed]
    return history


def av_iteration_advance(state_path: Path, run_root: Path, *,
                         authorization: Optional[Mapping[str, Any]] = None,
                         stop_after: Optional[str] = None,
                         max_advances: int = 24,
                         test_runtime_factory: Optional[
                             Callable[[], Mapping[str, Any]]] = None,
                         expected_identity: Optional[Mapping[str, Any]] = None,
                         ) -> Dict[str, Any]:
    """执行**下一步**（由落盘状态决定）并原子落盘；返回推进报告。

    - 每次调用至多推进 max_advances 步（默认覆盖整个状态机）；
    - stop_after=状态名：到达该状态即停（中断注入/演练用，模拟崩溃点）；
    - delegate 生成等待外部回复时返回 waiting_for_reply=True（不重发提示词）；
    - 终态（ITERATION_COMPLETE/REJECTED/...）幂等：重复调用不再执行。

    S2：本入口**自行重算冻结清单**并与开轮冻结值逐面比对，不一致即返回
    refused（不写状态、不产生新费用、不写新结果）；expected_identity 只是额外
    期望条件。S3：推进期间持有运行目录推进者锁（同一目录同时只有一个推进者），
    被占用即返回 refused（advancer_busy=True）。
    """

    state = av_state_load(state_path)
    run_root = Path(run_root)
    result: Dict[str, Any] = {"run_id": state.get("run_id")}
    # —— S2：每个推进入口**自行重算冻结清单**；不一致即拒绝（不写状态、不产生
    #    新费用、不写新结果）。身份核验先于推进者锁，二者都先于任何副作用。
    identity_ok, identity_reason, _manifest = av_verify_run_identity(
        state, expected=expected_identity, entry="advance")
    if not identity_ok:
        result.update({"status": state.get("status"), "advanced": [],
                       "identity_refused": True,
                       "refused": "身份核验失败（推进入口自算冻结清单）：{0}".format(
                           identity_reason)})
        return result
    try:
        with av_advancer_lock(run_root):
            return _av_advance_locked(state_path, run_root, state, result,
                                      authorization=authorization,
                                      stop_after=stop_after,
                                      max_advances=max_advances,
                                      test_runtime_factory=test_runtime_factory)
    except AdvancerBusy as error:
        result.update({"status": state.get("status"), "advanced": [],
                       "advancer_busy": True, "refused": str(error)})
        return result


def _av_advance_locked(state_path: Path, run_root: Path, state: Dict[str, Any],
                       result: Dict[str, Any], *,
                       authorization: Optional[Mapping[str, Any]],
                       stop_after: Optional[str], max_advances: int,
                       test_runtime_factory: Optional[
                           Callable[[], Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """持推进者锁执行状态机（S3：同一运行目录同时只有一个推进者）。"""

    # —— 跨目录连续恢复前置：已登记的调度输入内容必须仍是开轮那一份 ——
    # 换内容不改路径时，源码身份（冻结清单摘要）逐字不变，输入数据却已不是那一份：
    # 这里**拒绝恢复**并给出具名停因（不静默按新内容继续、不偷偷改写身份）。
    archive_input = av_archive_input_verify(state)
    state["archive_input"] = archive_input
    if not archive_input["ok"]:
        # 具名停因取自核验结果（漂移 / 身份缺失 / 快照缺失 / 快照字节不符 / 冻结失败）：
        # 一律在**执行与提交之前**停止，不按新内容继续、也不静默改写身份。
        state["stop_reason"] = (archive_input.get("stop_reason")
                                or AV_ARCHIVE_INPUT_DRIFT_STOP_REASON)
        av_state_history_append(
            state, "INPUT_GAP",
            "调度输入内容身份核验未通过：拒绝跨目录连续恢复（{0}）".format(
                archive_input.get("status")),
            archive_input=archive_input)
        av_state_save(state_path, state)
        result["status"] = state.get("status")
        result["terminal"] = "INPUT_GAP"
        result["archive_input"] = archive_input
        result["state"] = {key: value for key, value in state.items()
                           if key != "candidate_source"}
        return result
    advanced: List[str] = []
    for _ in range(max_advances):
        status = state.get("status")
        result["status"] = status
        if status in AV_TERMINAL_STATES or status == "ITERATION_COMPLETE":
            result["terminal"] = status
            break
        # 中断注入/演练：到达指定状态的落盘点即停（该状态已持久化，未执行其下一步）。
        if stop_after and status == stop_after:
            result["stopped_after"] = stop_after
            break
        ledger = _av_ledger_for_run(run_root, authorization)
        if status == "RESERVED":
            step_result = _step_generate(state, run_root, ledger, stop_after)
        elif status == "GENERATED":
            step_result = _step_admit(state)
        elif status == "ADMITTED":
            step_result = _step_behavior(state, run_root)
        elif status == "BEHAVIOR_CHECKED":
            step_result = _step_conditional(state, run_root, ledger, authorization,
                                            test_runtime_factory)
        elif status == "CONDITIONAL_EVALUATED":
            step_result = _step_natural(state, run_root, authorization)
        elif status == "NATURAL_EVALUATED":
            step_result = _step_summarize(state)
        elif status == "SUMMARIZED":
            step_result = _step_archive(state, run_root, ledger)
        elif status == "REFRESH_PENDING":
            # P7b：补根调度入口——按剩余预算为缺失身份补齐挑战点名的根，补齐后
            # 重试同一条提交路径（提交条件不变：全员齐备才换 epoch）。
            step_result = _step_refresh_fill(state, run_root, ledger, authorization,
                                             test_runtime_factory)
        elif status == "ARCHIVE_COMMITTED":
            step_result = _step_batch_end(state, run_root, ledger)
        else:
            raise ValueError("未知状态 {0!r}".format(status))
        av_state_save(state_path, state)
        # A4：终态提案（含失败/预算耗尽/执行失败/生成被拒）同样入不可变事件账本，
        # 占用提案额度；批末已入账的迭代由幂等键去重，不产生第二条口径。
        if (state.get("status") in AV_TERMINAL_STATES
                or state.get("status") == "ITERATION_COMPLETE"):
            av_proposal_event_record(run_root, state)
        if step_result.get("waiting_for_reply"):
            result["waiting_for_reply"] = True
            break
        if step_result.get("terminal"):
            result["terminal"] = step_result["terminal"]
            break
        if step_result.get("advanced"):
            advanced.append(step_result["advanced"])
            if step_result.get("still_pending"):
                # 刷新未补齐：保持旧席位并停下（等待外部补根材料；恢复幂等，
                # 不重复计费、不无限重试）。
                result["refresh_pending"] = True
                break
    result["advanced"] = advanced
    result["state"] = {key: value for key, value in state.items()
                       if key != "candidate_source"}
    return result


def av_latest_state_path(run_root: Path) -> Optional[Path]:
    """run_root 下最新迭代的状态文件；无迭代返回 None。"""

    iterations = Path(run_root) / "iterations"
    if not iterations.is_dir():
        return None
    candidates = sorted(iterations.glob("iter-*"))
    for iter_dir in reversed(candidates):
        state_path = iter_dir / "state.json"
        if state_path.is_file():
            return state_path
    return None


def run_av_evolution(out_dir: Path, *, generation_mode: str = "delegate",
                     seed_name: str = "efficiency_seed",
                     predicate: str = "branch_open", opponent: str = "H",
                     authorization: Optional[Mapping[str, Any]] = None,
                     reply_envelope: Optional[Path] = None,
                     natural_roots: int = 1, natural_seats: int = 1,
                     prefix_source: str = "scripted_fixture",
                     panel_seed: int = 20260916,
                     stop_after: Optional[str] = None,
                     resume_run_id: Optional[str] = None,
                     archive_path: Optional[Path] = None,
                     family_channel: Optional[str] = None,
                     family_refresh: Optional[Sequence[Mapping[str, Any]]] = None,
                     test_runtime_factory: Optional[
                         Callable[[], Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """evolve-action-value 生产入口：开新迭代或恢复在案迭代并推进到停点。

    - run_root 下无 state.json → av_start_iteration（operator 由**共享档案**的
      next_generation_plan 决定：档案有席位 → 按通道轮转 M1 + 父代；档案空 →
      I1）；
    - 有 state.json → 直接 advance（真实 resume：从当前步续跑，不重不漏）；
    - delegate 模式等待回复时返回 waiting_for_reply（带 pending 交接件路径）；
    - `archive_path`（CLI `--archive`）：显式指定共享档案，优先于自动发现；
      不给时按 av_discover_archive 自动发现（本目录 → 父子目录 iter-* 链最新的
      ARCHIVE_COMMITTED 产物 → 空档案）；显式路径不存在即拒绝开轮。
    - test_runtime_factory（**显式测试入口**）：条件步运行时装配的替身来源；只能
      返回经 build_test_runtime_double 装配的替身（否则拒绝）。生产路径不给该参数
      → 组合处经 build_real_runtime 装配真实运行时（A1）；装配失败即终态
      EXECUTION_FAILED，绝不回退替身/夹具。
    """

    out_dir = guard_out_dir(Path(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = av_latest_state_path(out_dir)
    if state_path is not None:
        latest = av_state_load(state_path)
        if latest.get("status") in AV_TERMINAL_STATES or latest.get(
                "status") == "ITERATION_COMPLETE":
            # 上一迭代已终态：开**新**迭代（同一 run_root 的持久档案/账本续用）。
            state_path = None
        elif resume_run_id is not None and latest.get("run_id") != resume_run_id:
            return {"ok": False, "refused": "run_id 不符（在案 {0}，本次 {1}）".format(
                latest.get("run_id"), resume_run_id)}
    if state_path is None:
        archive_mod = av_archive()
        # 调度输入档案：显式 --archive > 本目录 > 迭代目录链最新提交 > 空档案。
        discovered, discovery = av_discover_archive(out_dir, explicit=archive_path)
        if discovered is None and discovery.get("source") == "explicit_missing":
            return {"ok": False, "refused": (
                "显式 --archive 指向的档案不存在：{0}（fail-closed：不静默回退到"
                "自动发现或空档案）").format(discovery.get("path"))}
        archive = (json.loads(discovered.read_text(encoding="utf-8"))
                   if discovered is not None else {})
        history = _av_plan_history(out_dir)
        plan = archive_mod.next_generation_plan(archive, history)
        operator = "m1" if plan.get("operator") == "M1" else "i1"
        parent_dir = None
        if operator == "m1" and plan.get("parent_candidate_id"):
            parent_dir = _av_find_attempt_dir(out_dir, plan["parent_candidate_id"])
        if operator == "m1" and parent_dir is None:
            # 调度给 M1 但找不到可绑定父代产物：回退 I1 并记录（不凭空造父代）。
            operator = "i1"
        archive_in = _av_archive_in_record(discovered, discovery, archive,
                                           history, plan)
        archive_in.update({
            "applied_operator": operator,
            "applied_parent_dir": str(parent_dir) if parent_dir else None,
        })
        state = av_start_iteration(
            out_dir, operator=operator, predicate=predicate, opponent=opponent,
            generation_mode=generation_mode, seed_name=seed_name,
            natural_roots=natural_roots, natural_seats=natural_seats,
            prefix_source=prefix_source, panel_seed=panel_seed,
            parent_dir=parent_dir, archive_in=archive_in,
            family_channel=family_channel, family_refresh=family_refresh,
            authorization=authorization, reply_envelope=reply_envelope)
        state_path = Path(state["iter_dir"]) / "state.json"
    return av_iteration_advance(state_path, out_dir, authorization=authorization,
                                stop_after=stop_after,
                                test_runtime_factory=test_runtime_factory)


def _av_find_attempt_dir(run_root: Path, candidate_id: str) -> Optional[Path]:
    """按 candidate_id 在**迭代目录链**里找生成产物目录（M1 父代绑定用）。

    链 = 本目录 + 父目录下兄弟 iter-* 运行目录（跨 `--out iter-NN` 的父代就
    落在前序运行目录里）；每个运行目录内按迭代号倒序找（新产物优先）。找不到
    返回 None——调用方据此回退 I1，不凭空造父代。
    """

    for root in _av_chain_run_roots(run_root):
        for iter_dir in reversed(_av_iteration_dirs_in(root)):
            candidate_path = iter_dir / "generation" / "candidate.py"
            if not candidate_path.is_file():
                continue
            state_path = iter_dir / "state.json"
            state = av_state_load(state_path) if state_path.is_file() else {}
            if (state.get("identity") or {}).get("candidate_id") == candidate_id:
                return iter_dir / "generation"
    return None


def run_av_machine_resume(out_dir: Path, *, run_id: str,
                          identity: Optional[Mapping[str, Any]] = None,
                          authorization: Optional[Mapping[str, Any]] = None,
                          test_runtime_factory: Optional[
                              Callable[[], Mapping[str, Any]]] = None,
                          ) -> Dict[str, Any]:
    """真实 resume：读取落盘状态 → **入口自算冻结清单并核验** → 从当前步续跑到停点。

    S2：identity 参数只作**额外期望条件**（与入口重算值逐项比对，不满足即拒绝）；
    空缺 / 空映射都不是绕过形态——在案冻结清单与当前实现的重算结果才是门槛。
    S3：推进者锁与实例对账在 av_iteration_advance 内完成（同一运行目录单推进者）。
    """

    out_dir = Path(out_dir)
    state_path = av_latest_state_path(out_dir)
    if state_path is None:
        return {"schema": "sitin-action-value-resume/1", "ok": False,
                "refused": "运行目录没有可恢复的迭代状态（iterations/*/state.json）"}
    state = av_state_load(state_path)
    if state.get("run_id") != run_id:
        return {"schema": "sitin-action-value-resume/1", "ok": False,
                "refused": "run_id 不符（在案 {0}，本次 {1}）：拒绝续写".format(
                    state.get("run_id"), run_id)}
    # S2：入口自算冻结清单；调用方 identity 只作**额外期望条件**（不满足即拒绝），
    # 空 identity / 只给 run_id 都不是绕过形态——重算面与期望面都独立成立。
    matched, reason, _manifest = av_verify_run_identity(
        state, expected=identity, entry="resume")
    if not matched:
        return {"schema": "sitin-action-value-resume/1", "ok": False,
                "identity_refused": True,
                "refused": "身份核验失败（恢复入口自算冻结清单）：{0}".format(reason)}
    result = av_iteration_advance(state_path, out_dir, authorization=authorization,
                                  test_runtime_factory=test_runtime_factory)
    result.update({"schema": "sitin-action-value-resume/1", "ok": True,
                   "run_id": run_id,
                   "resumed_steps": [item.get("status")
                                     for item in state.get("step_history", [])]})
    return result

# ---------------------------------------------------------------------------
# 9.5 七命令 CLI 处理器（§13.1 表逐行；--help 退出码 0，证据写真实调用）
# ---------------------------------------------------------------------------


def cmd_validate_contract(args: Any) -> int:
    verdict = validate_action_value_contracts()
    write_json(Path(args.out) / "contract-validation.json", verdict) if args.out else None
    print(json.dumps({"ok": verdict["ok"], "problems": verdict["problems"],
                      "checks": sorted(verdict["checks"])}, ensure_ascii=False))
    return 0 if verdict["ok"] else 2


def cmd_forward_build_panel(args: Any) -> int:
    """build-panel：转发 C1 CLI（同目录 sitin_opportunities build-panel）。"""

    opportunities = av_opportunities()
    argv = ["build-panel", "--prefix-source", args.prefix_source,
            "--sub-scenario", args.sub_scenario, "--opponent", args.opponent,
            "--focal-seat", str(args.focal_seat), "--out", args.out,
            "--attempts-cap", str(args.attempts_cap), "--panel-seed", str(args.panel_seed)]
    if args.v2_authorization:
        argv += ["--v2-authorization", args.v2_authorization]
    return int(opportunities.main(argv) or 0)


def cmd_admit_action_value(args: Any) -> int:
    source = Path(args.candidate_source).read_text(encoding="utf-8")
    record_dir = Path(args.record_dir) if args.record_dir else None
    admission = av_gates().admit_action_value(
        source,
        executor_config={"timeout_sec": args.timeout_sec},
        facts_panel={"generator": av_opportunities().GENERATOR_SCRIPTED_FIXTURE,
                     "legal": True,
                     "record_dir": str(record_dir) if record_dir else None},
        timing_config={"repeats": args.repeats})
    if record_dir:
        write_json(Path(record_dir) / "admission.json", admission)
    print(json.dumps({
        "schema": admission["schema"],
        "execution_safety": admission["layers"]["execution_safety"]["status"],
        "coverage": admission["layers"]["coverage"]["status"],
        "controlled_research": admission["layers"]["controlled_research"]["status"],
        "timing": admission["timing"].get("status"),
        "candidate_id": admission["identity"]["candidate_id"],
    }, ensure_ascii=False))
    return 0 if admission["execution_safety_pass"] else 1


def cmd_evaluate_action_value(args: Any) -> int:
    source = Path(args.candidate_source).read_text(encoding="utf-8")
    authorization = None
    if args.real_authorization:
        authorization = json.loads(Path(args.real_authorization).read_text(encoding="utf-8"))
    prefix_source = str(getattr(args, "prefix_source", "scripted_fixture"))
    if prefix_source == "v2_behavior":
        # 真实模式路由纪律：--real-authorization 与 --v2-authorization 必须同给
        # （可指向同一文件）；缺任一即拒绝，不静默降级到夹具。
        missing = [flag for flag, value in (
            ("--real-authorization", args.real_authorization),
            ("--v2-authorization", getattr(args, "v2_authorization", None))) if not value]
        if missing:
            print(json.dumps({
                "ok": False, "refused": ("v2_behavior 真实评估要求 {0} 同给（可同文件）；"
                                         "缺 {1} 即拒绝，不静默降级 scripted_fixture").format(
                    "--real-authorization 与 --v2-authorization", "、".join(missing)),
            }, ensure_ascii=False))
            return 3
    # A1 修复（复审 P1）：正式 CLI 在**组合处显式装配真实运行时**并显式下传；
    # 装配失败即拒绝——旧行为（缺省注入公开契约验证替身）已删除。
    runtime = None
    if prefix_source == "v2_behavior":
        from hangma_bot.kernel.config import RuleConfig

        opportunities = av_opportunities()
        try:
            runtime = opportunities.build_real_runtime(
                rules_config=RuleConfig(AV_CONDITIONAL_RULESET_VERSION, 1, False),
                rounds_per_game=AV_CONDITIONAL_ROUNDS_PER_GAME,
                scenario_id="sitin-evaluate-action-value")
        except Exception as error:  # 装配失败：拒绝，不做替身/夹具回退
            print(json.dumps({
                "ok": False,
                "refused": "真实运行时装配失败（fail-closed，不回退替身）：{0}: {1}".format(
                    type(error).__name__, error),
            }, ensure_ascii=False))
            return 3
    try:
        evaluation = run_av_evaluation(guard_out_dir(Path(args.out)), source,
                                       predicate=args.sub_scenario, opponent=args.opponent,
                                       authorization=authorization,
                                       attempts_cap=args.attempts_cap,
                                       panel_seed=args.panel_seed,
                                       prefix_source=prefix_source,
                                       runtime=runtime)
    except av_opportunities().RuntimeAssemblyError as error:
        print(json.dumps({"ok": False, "refused": "运行时装配未通过：{0}".format(error)},
                         ensure_ascii=False))
        return 3
    print(json.dumps({
        "ok": evaluation.get("ok"),
        "evaluation_id": (evaluation.get("identity") or {}).get("evaluation_id"),
        "double_arm_valid": (evaluation.get("double_arm") or {}).get("valid"),
        "prefix_source": evaluation.get("prefix_source", prefix_source),
        "real_table_instances": evaluation.get("real_table_instances", 0),
        "refused": evaluation.get("refused"),
    }, ensure_ascii=False))
    if evaluation.get("refused"):
        return 3
    return 0 if evaluation.get("ok") else 1


def cmd_evolve_action_value(args: Any) -> int:
    """evolve-action-value：R5 状态机编排（持久 state.json，逐步原子落盘）。

    缺省 delegate 文件式生成（产 pending 交接件后停下等回复，resume 续跑
    不重发）；--generation-mock 为显式测试模式（种子包装，血缘标注）。
    """
    authorization = None
    if args.real_authorization:
        authorization = json.loads(Path(args.real_authorization).read_text(encoding="utf-8"))
    generation_mode = "mock" if args.generation_mock else "delegate"
    result = run_av_evolution(guard_out_dir(Path(args.out)),
                              generation_mode=generation_mode,
                              seed_name=args.seed,
                              predicate=args.sub_scenario, opponent=args.opponent,
                              authorization=authorization,
                              reply_envelope=(Path(args.reply_envelope)
                                              if args.reply_envelope else None),
                              natural_roots=args.natural_roots,
                              natural_seats=args.natural_seats,
                              prefix_source=args.prefix_source,
                              stop_after=args.stop_after_state,
                              archive_path=(Path(args.archive)
                                            if getattr(args, "archive", None)
                                            else None))
    state = result.get("state") or {}
    print(json.dumps({
        "run_id": result.get("run_id"),
        "status": result.get("status") or state.get("status"),
        "advanced": result.get("advanced"),
        "waiting_for_reply": bool(result.get("waiting_for_reply")),
        "stopped_after": result.get("stopped_after"),
        "terminal": result.get("terminal"),
        "pending_dir": ((state.get("generation") or {}).get("pending_dir")),
        # 调度输入档案（哪一份档案、来源、条目/席位、结论）——跨迭代传递的可核对证据。
        "archive_in": (state.get("plan") or {}).get("archive_in"),
        "refused": result.get("refused"),
    }, ensure_ascii=False))
    if result.get("refused"):
        return 3
    if result.get("waiting_for_reply"):
        return 4
    terminal = result.get("terminal")
    if terminal == "ITERATION_COMPLETE":
        return 0
    if terminal in AV_TERMINAL_STATES:
        return 1
    return 0


def cmd_confirm_action_value(args: Any) -> int:
    confirm_authorization = None
    if args.confirm_authorization:
        confirm_authorization = json.loads(
            Path(args.confirm_authorization).read_text(encoding="utf-8"))
    result = run_av_confirm(guard_out_dir(Path(args.out)), Path(args.archive),
                            Path(args.epoch),
                            confirm_budget=args.budget,
                            confirm_authorization=confirm_authorization,
                            extra_evaluations=(json.loads(Path(args.extra_evaluations)
                                                          .read_text(encoding="utf-8"))
                                               if args.extra_evaluations else None))
    print(json.dumps({"ok": result.get("ok"), "refused": result.get("refused"),
                      "nominated": (result.get("nomination") or {}).get("nominated")},
                     ensure_ascii=False))
    return 0 if result.get("ok") else 3


def cmd_resume_action_value(args: Any) -> int:
    """resume：真实恢复——读 state.json → 核验身份 → 从当前步续跑到停点。"""
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8")) \
        if getattr(args, "identity", None) else None
    authorization = None
    if getattr(args, "real_authorization", None):
        authorization = json.loads(Path(args.real_authorization)
                                   .read_text(encoding="utf-8"))
    machine = run_av_machine_resume(Path(args.run_dir), run_id=args.run_id,
                                    identity=identity, authorization=authorization)
    if not machine.get("refused"):
        print(json.dumps({
            "ok": True, "run_id": machine.get("run_id"),
            "status": machine.get("status"),
            "advanced": machine.get("advanced"),
            "waiting_for_reply": bool(machine.get("waiting_for_reply")),
            "terminal": machine.get("terminal"),
        }, ensure_ascii=False))
        return 4 if machine.get("waiting_for_reply") else 0
    # 无状态机目录时回退旧报告式核验（兼容 legacy iteration.json 运行目录）。
    if identity:
        legacy = run_av_resume(Path(args.run_dir), run_id=args.run_id, identity=identity)
        print(json.dumps({"ok": legacy.get("ok"),
                          "refused": legacy.get("refused"),
                          "legacy": True}, ensure_ascii=False))
        return 0 if legacy.get("ok") else 2
    print(json.dumps({"ok": False, "refused": machine.get("refused")},
                     ensure_ascii=False))
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="坐隐 3.4/3.5：搜索闭环驱动与冻结交接（只串联与记账，不重实现）")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_pool(target: argparse.ArgumentParser) -> None:
        target.add_argument("--pool", default=None,
                            help="候选池 JSON（schema {0}）".format(POOL_SCHEMA))
        target.add_argument("--candidate", action="append", default=[], help="候选名，可重复")
        target.add_argument("--weights", action="append", default=[],
                            help="与 --candidate 一一对应的 JSON；缺省为 {}")

    plan = sub.add_parser("plan", help="按冻结预算核算本批规模（不改任何预算）")
    plan.add_argument("--freeze", required=True)
    plan.add_argument("--out", required=True)
    plan.add_argument("--available", type=int, default=None,
                      help="实际可执行候选数（缺省取候选池大小）")
    add_pool(plan)
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="执行搜索闭环（先预留后执行；超限即停）")
    run.add_argument("--freeze", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--gate-records", action="append", required=True,
                     help="准入记录目录（**可重复**：记录由各包落在自己的可写目录，消费侧同时读多处）")
    run.add_argument("--admission-corpus", required=True, help="准入记录所依据的决策语料")
    run.add_argument("--generation-plan", default=None, help="生成请求清单 JSON")
    run.add_argument("--level-name", default="L1")
    # 升级级名可声明：台账按步 id 唯一（防重复计费），"同一本账里再加一个候选"必须能命名两级，
    # 否则第二级会撞上已完成的 screen:L2 被判"复用"、拿不到样本。面板身份与等级名无关
    # （只由 seed + 换座 + 基线 + 规则版本决定），因此改名不改变可比性。
    run.add_argument("--upgrade-level-name", default="L2")
    # 逐条点名已报告的超限步，允许**继续执行后续步骤**（可重复；不对已结算数字做任何修改）。
    run.add_argument("--acknowledge-overrun", action="append", default=[], metavar="STEP_ID",
                     help="点名一个已报告且已记账的超限步，记录知情例外后继续（不改 charged、不清 overrun）")
    run.add_argument("--legacy-wall-basis", default=None,
                     help="显式一次性处置：本冻结件产生于 fail-closed 规则之前，墙钟口径为历史值（一句话原因）")
    run.add_argument("--gen-timeout-sec", type=float, default=900.0)
    run.add_argument("--gen-token-reserve", type=int, default=32768,
                     help="单次生成预留的输出 token（先预留、按实测结算）")
    run.add_argument("--screen-timeout-sec", type=float, default=None)
    run.add_argument("--stage-contract", default=None, help="阶段合同 JSON（阶段比较用）")
    run.add_argument("--dry-run", action="store_true", help="只做预留与命令渲染，不真跑")
    run.add_argument("--allow-rerun", action="store_true",
                     help="允许重演已完成的步（照常计费，标记 rerun）")
    add_pool(run)
    run.set_defaults(func=cmd_run)

    stage = sub.add_parser("stage", help="只执行阶段比较一步（新冻结、新账本）")
    stage.add_argument("--freeze", required=True)
    stage.add_argument("--out", required=True)
    stage.add_argument("--from-archive", required=True, help="既有档案（播种身份与准入依据）")
    stage.add_argument("--candidates", required=True, help="逗号分隔的档案键")
    stage.add_argument("--gate-records", required=True)
    stage.add_argument("--admission-corpus", required=True)
    stage.add_argument("--stage-contract", required=True)
    stage.add_argument("--dry-run", action="store_true")
    stage.add_argument("--legacy-wall-basis", default=None,
                        help="显式一次性处置：本冻结件产生于 fail-closed 规则之前，墙钟口径为历史值（一句话原因）")
    stage.add_argument("--allow-rerun", action="store_true")
    stage.set_defaults(func=cmd_stage)

    status = sub.add_parser("status", help="打印台账/档案/状态")
    status.add_argument("--out", required=True)
    status.set_defaults(func=cmd_status)

    freeze = sub.add_parser("freeze", help="产出 3.5 交接报告（三种完成状态分开报）")
    freeze.add_argument("--freeze", required=True)
    freeze.add_argument("--out", required=True)
    freeze.add_argument("--stage-gap-reason", default=None)
    freeze.add_argument("--also", action="append", default=[],
                        help="额外的产物目录（各自一本账）：交接报告按候选合并、预算分账并列")
    freeze.add_argument("--dev-spend", default=None,
                        help="开发期消耗清单 JSON（登记用：不进搜索账 spent，也不进上限分母）")
    freeze.add_argument("--pre-kernel-reference", action="append", default=None,
                        help="启用内核前的口径来源（旧冻结件/旧报告）；交接件把它列进 pre_kernel_references")
    freeze.add_argument("--throughput-env", action="append", default=None,
                        help="机时口径产物（throughput-probe 报告 / check_native_backend --json）；"
                             "可重复，交接件按每个报告自己的后端分成 post/pre kernel 两块")
    freeze.add_argument("--legacy-wall-basis", default=None,
                        help="显式一次性处置：当所汇总的账里有冻结件缺 wall_estimate_sec_per_table 时必须给出")
    freeze.add_argument("--gate-records", action="append", default=None,
                        help="门禁记录目录（**可重复**）：按当前记录重扫并修正报告里的 gate 字段")
    freeze.add_argument("--admission-corpus", default=None,
                        help="准入语料（重扫时校验 corpus.sha256；不传则重扫判 no_corpus）")
    freeze.add_argument("--stage-evidence", default=None,
                        help="阶段证据取代关系 JSON（外部运行可取代结论，但按开发期消耗登记）")
    add_pool(freeze)
    freeze.set_defaults(func=cmd_freeze)

    verify = sub.add_parser("verify-injection",
                            help="参数注入行为核验（诊断步；计划写在冻结文件的 verify 段）")
    verify.add_argument("--freeze", required=True)
    verify.add_argument("--out", required=True)
    verify.add_argument("--dry-run", action="store_true")
    verify.add_argument("--legacy-wall-basis", default=None,
                        help="显式一次性处置：本冻结件产生于 fail-closed 规则之前，墙钟口径为历史值（一句话原因）")
    verify.set_defaults(func=cmd_verify_injection)

    wiring = sub.add_parser("verify-wiring",
                            help="触发面接线验证（0 桌）：分支是否被触发、参数是否改变分数")
    wiring.add_argument("--freeze", required=True)
    wiring.add_argument("--out", required=True)
    wiring.add_argument("--dry-run", action="store_true")
    wiring.set_defaults(func=cmd_verify_wiring)

    correct = sub.add_parser("correct", help="更正台账里已知是错的数字（留痕，不重结）")
    correct.add_argument("--freeze", required=True)
    correct.add_argument("--out", required=True)
    correct.add_argument("--reservation-id", required=True)
    correct.add_argument("--axis", required=True, choices=list(AXES))
    correct.add_argument("--value", required=True)
    correct.add_argument("--note", required=True)
    correct.set_defaults(func=cmd_correct)

    arm = sub.add_parser("internal-throughput-arm", help="内部入口：进程内跑一臂并写计数器")
    arm.add_argument("--repo-root", required=True)
    arm.add_argument("--experiment", required=True)
    arm.add_argument("--out", required=True)
    arm.add_argument("--counters", required=True)
    arm.add_argument("--native", default=None,
                     help="编译内核路径（.so）：按 probe.py 的同一方式换进热路径，并校验语义版本")
    arm.set_defaults(func=cmd_internal_throughput_arm)
    thr = sub.add_parser("throughput-probe",
                         help="吞吐诊断账：把历史实验配置在当前运行时重跑，对拍 CPU 秒/桌（臂由冻结件声明）")
    thr.add_argument("--freeze", required=True)
    thr.add_argument("--out", required=True)
    thr.add_argument("--dry-run", action="store_true")
    thr.add_argument("--legacy-wall-basis", default=None,
                        help="显式一次性处置：本冻结件产生于 fail-closed 规则之前，墙钟口径为历史值（一句话原因）")
    thr.add_argument("--plan", default=None,
                     help="已冻结的计划文件（覆盖冻结件的 throughput_probe 段；其 sha256 记入报告）")
    thr.add_argument("--step", default=None,
                     help="本步的标签（默认 throughput）：同一本账里做第二种诊断时用它避开已完成的步 id）")
    thr.add_argument("--rerun", action="store_true",
                     help="显式重跑（仅用于上一次标记完成但未产出可用结果；计费照常，账本会拒绝重复占用）")
    thr.set_defaults(func=cmd_throughput_probe)
    probe = sub.add_parser("probe-stage", help="探阶段面板能否坐进候选（不消耗预算）")
    probe.add_argument("--freeze", required=True)
    probe.add_argument("--out", required=True)
    probe.add_argument("--candidate", required=True, help="待探的候选/面板策略名")
    probe.set_defaults(func=cmd_probe_stage)

    # ---- action_value_v1 七命令路由（§13.1 表逐行；D 包新增，不动旧子命令）----
    here = str(Path(__file__).resolve())
    av_epilog = (
        "真实调用示例（零预算 fail-closed 路由验收，全部离线）：\n"
        "  {py} {f} validate-contract\n"
        "  {py} {f} build-panel --prefix-source scripted_fixture"
        " --sub-scenario branch_open --opponent H --out /tmp/av-panel\n"
        "  {py} {f} admit-action-value --candidate-source <candidate.py>"
        " --record-dir /tmp/av-admit\n"
        "  {py} {f} evaluate-action-value --candidate-source <candidate.py>"
        " --sub-scenario branch_open --opponent H --out /tmp/av-eval\n"
        "  {py} {f} evaluate-action-value --candidate-source <candidate.py>"
        " --prefix-source v2_behavior --sub-scenario branch_open --opponent H"
        " --out /tmp/av-eval-v2 --real-authorization <auth.json>"
        " --v2-authorization <auth.json>\n"
        "  {py} {f} evolve-action-value --seed efficiency_seed --out /tmp/av-iter\n"
        "  {py} {f} confirm-action-value --archive <av-archive.json>"
        " --epoch <epoch.json> --out /tmp/av-confirm\n"
        "  {py} {f} resume --run-dir /tmp/av-iter --run-id <run_id>"
        " --identity <identity.json>"
    ).format(py=sys.executable, f=here)

    vc = sub.add_parser(
        "validate-contract",
        help="校验 contracts/*.json 两份合同并与执行器对账（白名单/限额/签名/上限）")
    vc.add_argument("--out", default=None, help="校验结果 JSON 写出路径（可省）")
    vc.set_defaults(func=cmd_validate_contract)

    bp = sub.add_parser(
        "build-panel", help="转发 C1 sitin_opportunities build-panel（离线夹具面板）")
    bp.add_argument("--prefix-source", default="scripted_fixture",
                    choices=("scripted_fixture", "v2_behavior"))
    bp.add_argument("--sub-scenario", default="branch_open")
    bp.add_argument("--opponent", default="H", choices=("H", "M"))
    bp.add_argument("--focal-seat", type=int, default=0, choices=(0, 1, 2, 3))
    bp.add_argument("--out", required=True)
    bp.add_argument("--attempts-cap", type=int, default=256)
    bp.add_argument("--panel-seed", type=int, default=20260916)
    bp.add_argument("--v2-authorization", default=None,
                    help="v2_behavior 的批次 7 授权令牌 JSON；缺失即拒绝")
    bp.set_defaults(func=cmd_forward_build_panel)

    adm = sub.add_parser(
        "admit-action-value",
        help="action_value_v1 五层门禁（sitin-action-value-admission/1 独立记录）")
    adm.add_argument("--candidate-source", required=True, help="候选源码文件")
    adm.add_argument("--record-dir", default=None, help="门禁记录目录（独立记录文件）")
    adm.add_argument("--timeout-sec", type=float, default=60.0)
    adm.add_argument("--repeats", type=int, default=12, help="整链计时重复次数")
    adm.set_defaults(func=cmd_admit_action_value)

    ev = sub.add_parser(
        "evolve-action-value-alias", help="占位（真实命令见 evaluate-action-value）")
    ev.set_defaults(func=lambda args: 0)

    eva = sub.add_parser(
        "evaluate-action-value",
        help="候选→admit→C1 双臂→C2 统计→三段反馈→账本（缺省夹具；"
             "--prefix-source v2_behavior 走批次 7 授权前缀路由）")
    eva.add_argument("--candidate-source", required=True)
    eva.add_argument("--sub-scenario", default="branch_open")
    eva.add_argument("--opponent", default="H", choices=("H", "M"))
    eva.add_argument("--out", required=True)
    eva.add_argument("--attempts-cap", type=int, default=8)
    eva.add_argument("--panel-seed", type=int, default=20260916)
    eva.add_argument("--prefix-source", default="scripted_fixture",
                    choices=("scripted_fixture", "v2_behavior"),
                    help="前缀来源：缺省夹具（原行为不变）；v2_behavior 需批次 7 授权")
    eva.add_argument("--real-authorization", default=None,
                     help="真实桌赛授权 JSON（authorized=true）；缺省 fail-closed")
    eva.add_argument("--v2-authorization", default=None,
                     help="v2_behavior 前缀授权 JSON（authorized=true 且 batch=7；"
                          "真实模式与 --real-authorization 同给，可同文件）")
    eva.set_defaults(func=cmd_evaluate_action_value)

    evo = sub.add_parser(
        "evolve-action-value",
        description=("R5 状态机编排：RESERVED→GENERATED→ADMITTED→BEHAVIOR_CHECKED→"
                     "CONDITIONAL_EVALUATED+NATURAL_EVALUATED→SUMMARIZED→"
                     "REFRESH_PENDING/ARCHIVE_COMMITTED→ITERATION_COMPLETE。"
                     "每步 state.json 原子落盘（tmp+rename）；中断后 resume 从当前步"
                     "续跑不重不漏；delegate 生成产 pending 交接件后停下等回复"
                     "（exit 4），回复 envelope 出现后继续解析不重发；"
                     "--generation-mock 为显式测试模式。"),
        help="R5 状态机编排（持久 state.json；中断 resume 续跑不重不漏）")
    evo.add_argument("--seed", default="efficiency_seed",
                     help="--generation-mock 模式所用种子（显式测试模式）")
    evo.add_argument("--sub-scenario", default="branch_open")
    evo.add_argument("--opponent", default="H", choices=("H", "M"))
    evo.add_argument("--out", required=True)
    evo.add_argument("--real-authorization", default=None,
                     help="授权令牌 JSON（批次 7 真实执行 + budgets 账户额度）")
    evo.add_argument("--generation-mock", action="store_true",
                     help="显式测试模式：种子包装成回复（血缘标 offline_mock_fixture）；"
                          "缺省 delegate 文件式通道（产 pending 交接件后停下等回复）")
    evo.add_argument("--reply-envelope", default=None,
                     help="delegate 模式的回复 envelope 路径（缺省 <迭代目录>/reply-envelope.json；"
                          "文件出现后 resume 继续解析，不重发提示词）")
    evo.add_argument("--prefix-source", default="scripted_fixture",
                     choices=("scripted_fixture", "v2_behavior"),
                     help="条件面板前缀来源（v2_behavior 需批次 7 授权）")
    evo.add_argument("--natural-roots", type=int, default=1,
                     help="自然面板根数（每根 seats×2 臂×2 桌记 tables_full）")
    evo.add_argument("--natural-seats", type=int, default=1,
                     help="自然面板每根焦点座位数（1..4）")
    evo.add_argument("--archive", default=None,
                     help="跨迭代共享档案 JSON（R4 apply_challenge persist 产物或迭代"
                          "目录链中最新的 archive.json）；缺省自动发现：扫 --out 父目录下"
                          "兄弟 iter-*/iterations/*/ 的 ARCHIVE_COMMITTED 产物取 mtime 最新；"
                          "都没有才回退空档案（I1）")
    evo.add_argument("--stop-after-state", default=None, metavar="STATE",
                     help="中断注入/演练：到达该状态即停（RESERVED/GENERATED/...）")
    evo.set_defaults(func=cmd_evolve_action_value)

    cf = sub.add_parser(
        "confirm-action-value",
        help="C2 nominate + 确认预算门：无确认额度即拒并说明（confirm 硬禁继承）；"
             "当前只到提名——confirmation_executor=pending，不冒充确认结果")
    cf.add_argument("--archive", required=True)
    cf.add_argument("--epoch", required=True)
    cf.add_argument("--budget", type=float, default=None)
    cf.add_argument("--confirm-authorization", default=None,
                    help="独立确认授权 JSON（confirm_budget>0 且 authorized=true）")
    cf.add_argument("--extra-evaluations", default=None)
    cf.add_argument("--out", required=True)
    cf.set_defaults(func=cmd_confirm_action_value)

    rs = sub.add_parser(
        "resume",
        description=("真实恢复：读迭代目录 state.json → 核验身份（提供的字段逐项"
                     "匹配，任何不符拒绝续写）→ 从当前步续跑到停点。delegate 生成"
                     "等待回复时回复 envelope 放 <迭代目录>/reply-envelope.json 后"
                     "再 resume。"),
        help="真实恢复：读 state.json → 核验身份 → 从当前步续跑到停点；"
             "任何身份不符拒绝续写")
    rs.add_argument("--run-dir", required=True)
    rs.add_argument("--run-id", required=True)
    rs.add_argument("--identity", default=None,
                    help="身份 JSON（提供的字段逐项核验：candidate_id/evaluation_id/"
                         "panel_epoch/contract_sha256 等）")
    rs.add_argument("--real-authorization", default=None,
                    help="授权令牌 JSON（恢复时继续用同一共享账本）")
    rs.set_defaults(func=cmd_resume_action_value)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
