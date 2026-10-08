"""坐隐 2.4：顺序淘汰调度器（分级评估 + 小样本方差估计）。

**判据**（README §17 2.4）：能在预算内跑完一轮；**到预算即停，不静默扩容**。

**两条来自一手核对的教训**：

1. **预算台账必须独立于日志**。MEoH 把 `_tot_sample_nums += 1` 写在
   `if self._profiler is not None:` 块里（`vendor/LLM4AD@ffb6acf` `meoh.py:158-163`），
   结果**不挂 profiler 时样本预算永不触发**。本模块的台账是**先记账后执行**的
   独立对象，落盘与任何日志/分析无关。
2. **独立单位始终是根组**，不是桌、不是配对、不是换座（README §6.2、审查 R-1/R2-2）。
   因此方差估计一律先用**根内平均**，再用**根级**样本标准差算标准误；
   **禁止用 `n = 配对×双臂` 推 SE**——那正是初版 §1.2 犯过的错。

**边界**：淘汰是**开发期预算分配规则**，不声称每次淘汰都有统计证据，
也不声称只淘汰了"统计上明确变坏"的候选。本轮结果**不构成效果证据**。
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
import hashlib
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO_ROOT / "src")))

# **不在这里导入候选注册表**（REVIEW-9「装载有界」）：`policy.heuristics.__init__`
# 会 import 全部已注册候选模块，一个在模块体里挂住的候选会让调度器在**任何检查之前**
# 挂死。需要注册表时走 `heuristics_registry()`（惰性），而候选代码的执行一律
# 放进 `sitin_gates.supervised_prepare` 的隔离子进程。
_HEURISTICS: Optional[Any] = None


def heuristics_registry():
    """惰性导入候选注册表；只在**非受监管的兼容路径**（测试构造产物）里使用。"""

    global _HEURISTICS
    if _HEURISTICS is None:
        from hangma_bot.policy import heuristics as module
        _HEURISTICS = module
    return _HEURISTICS

SCHEMA = "sitin-scheduler/2"   # 2：新增 root_sets 与重演/新增样本的区分（R7-4）
RUN_STATE_SCHEMA = "sitin-run-state/1"   # 分级执行的持久化状态（R7-3）

# 顺序淘汰配方（README §6.2）。roots/seats 是**每候选**的量。
ROUND_SPECS: Tuple[Dict[str, Any], ...] = (
    {"name": "第一轮", "roots": 16, "seats": 2, "keep_fraction": 0.5},
    {"name": "第二轮", "roots": 64, "seats": 4, "keep_fraction": 0.25},
)

# 双侧 5%、80% 功效的分位数（与 sitin_power 同口径）
Z_ALPHA_TWO_SIDED = 1.9599639845
Z_POWER_80 = 0.8416212336

# 单轮评估的默认墙钟上限（REVIEW-7 2.5）：下限 + 每桌预算。
# 口径是"**异常**检测"而不是"性能门禁"：实测 1.466 秒/桌单核，
# 这里给到 ~20 倍余量，只拦死循环/阻塞这类不会自己结束的运行。
ROUND_TIMEOUT_FLOOR_SEC = 120.0
ROUND_TIMEOUT_PER_TABLE_SEC = 30.0
#: SIGTERM 之后给多久再 SIGKILL。
_TERMINATE_GRACE_SEC = 5.0


def round_timeout_sec(tables: int) -> float:
    """按本轮实际桌数给出墙钟上限（秒）。"""

    return ROUND_TIMEOUT_FLOOR_SEC + ROUND_TIMEOUT_PER_TABLE_SEC * max(0, int(tables))


class BudgetExceeded(RuntimeError):
    """预算不足；**必须显式停止，不得静默扩容**。"""


class RoundFailed(RuntimeError):
    """一轮评估没有产出可用结果（超时/非零退出/无法配对）。

    与 `BudgetExceeded` **分开**：预算不足是**计划**问题（停止并报告），
    运行失败是**候选或环境**问题（该候选不可排序，其余候选照常推进）。
    两者都不静默扩容，也都不把缺失值补零（REVIEW-7 R7-2）。
    """

    def __init__(self, message: str, *, returncode: Optional[int] = None,
                 stdout: str = "", stderr: str = "",
                 timeout_sec: Optional[float] = None,
                 supervision: Optional[Mapping[str, Any]] = None,
                 problems: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.timeout_sec = timeout_sec
        #: 受监管执行的结局（被杀/自然退出、发过哪些信号、组是否清空）。
        self.supervision = dict(supervision) if supervision is not None else None
        #: 计划核验发现的问题（R8-4）；空表示矩阵完整。
        self.problems = list(problems)

    def to_json(self) -> Dict[str, Any]:
        """落盘的失败证据；**保留输出尾部**，否则事后无法判断是超时还是崩了。"""

        payload = {
            "schema": "sitin-round-failure/1",
            "reason": str(self),
            "returncode": self.returncode,
            "timeout_sec": self.timeout_sec,
            "stdout_tail": self.stdout[-_FAILURE_TAIL_CHARS:],
            "stderr_tail": self.stderr[-_FAILURE_TAIL_CHARS:],
            "problems": list(self.problems),
        }
        if self.supervision is not None:
            payload["supervision"] = self.supervision
        return payload


#: 失败证据里保留的输出字符数（尾部，正常报错都在最后几行）。
_FAILURE_TAIL_CHARS = 2000


@dataclass
class BudgetLedger:
    """独立预算台账：**先记账后执行**，与日志/分析无关。

    `tables`：实际双臂桌数 = 根组数 × 换座数 × 2（每根每换座要跑基线与候选各一桌）。
    台账同时记录**消耗过的根组身份**，防止同一批开发根组被反复当作新证据。
    """

    table_budget: int
    spent_tables: int = 0
    rounds: List[Dict[str, Any]] = field(default_factory=list)
    consumed_root_keys: List[str] = field(default_factory=list)
    #: 每次预留的**根组集合身份**（R7-4）：用来区分新增样本 / 重演。
    root_sets: List[Dict[str, Any]] = field(default_factory=list)
    path: Optional[Path] = None

    @property
    def remaining_tables(self) -> int:
        return self.table_budget - self.spent_tables

    @property
    def exhausted(self) -> bool:
        return self.remaining_tables <= 0

    def can_afford(self, tables: int) -> bool:
        return tables <= self.remaining_tables

    def reserve(self, round_name: str, candidates: Sequence[str], roots: int,
                seats: int, root_keys: Sequence[str], *,
                root_set_id_value: Optional[str] = None,
                allow_rerun: bool = False) -> int:
        """预留本轮预算并**立即落盘**；不足则抛错（不静默扩容）。

        先记账后执行：即使执行阶段崩溃，台账也已经反映了这笔开销，
        不会因为"没跑到写日志那一步"而把预算花超。

        **R7-4：根组消费的防重语义。** 判重键是（轮次, 根组集合身份，按 **seed** 计算），
        再次预留属于**重演**，必须显式 allow_rerun=True；重演照常计费，但在台账里标记
        rerun=True，**不计入新增独立根组**。
        同一级里多个候选共用同一批根组是**允许且有用**的——它们在**同一次 reserve**
        里一起预留（tables 已乘以候选数），因此不会触发判重。
        """

        # R7-6：初版不校验，--seats -1 会**增加**剩余预算（记 −8 桌）
        # 而切片仍生成 3 次换座（24 桌）——记账与计划方向相反。
        if roots < 1:
            raise ValueError("根组数必须 >= 1，得到 {0}".format(roots))
        if not 1 <= seats <= 4:
            raise ValueError("换座数必须在 1—4，得到 {0}".format(seats))
        if not candidates:
            raise ValueError("候选列表不得为空")
        tables = roots * seats * 2 * len(candidates)
        set_id = root_set_id_value or root_set_id_of(root_keys)
        repeated = any(item.get("round") == round_name
                       and item.get("root_set_id") == set_id
                       for item in self.root_sets)
        if repeated and not allow_rerun:
            raise ValueError(
                "根组集合 {0} 在轮次 {1} 已被消费：这是**重演**，"
                "不得当作新增独立样本。确需重演请显式 allow_rerun"
                "（会照常计费并在台账标记 rerun=true）。".format(set_id, round_name))
        if not self.can_afford(tables):
            raise BudgetExceeded(
                "本轮需要 {0} 桌，剩余 {1} 桌（预算 {2}，已用 {3}）；"
                "**到预算即停，不静默扩容**".format(
                    tables, self.remaining_tables, self.table_budget, self.spent_tables))
        self.spent_tables += tables
        self.rounds.append({"round": round_name, "candidates": list(candidates),
                            "roots": roots, "seats": seats, "tables": tables,
                            "root_keys": list(root_keys),
                            "root_set_id": set_id, "rerun": bool(repeated)})
        self.root_sets.append({"round": round_name, "root_set_id": set_id,
                               "roots": roots, "seats": seats,
                               "candidates": list(candidates), "tables": tables,
                               "rerun": bool(repeated)})
        self.consumed_root_keys.extend(root_keys)
        self.save()
        return tables

    def to_json(self) -> Dict[str, Any]:
        return {"schema": SCHEMA, "table_budget": self.table_budget,
                "spent_tables": self.spent_tables,
                "remaining_tables": self.remaining_tables,
                "rounds": self.rounds,
                "root_sets": self.root_sets,
                "consumed_root_keys": sorted(set(self.consumed_root_keys))}

    def save(self) -> None:
        """落盘台账。**与任何日志/分析无关**——这是 E-2 教训的直接应用。"""

        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    @classmethod
    def load(cls, path: Path, table_budget: Optional[int] = None) -> "BudgetLedger":
        """读回台账；**命令行只能追加预算，不能缩减**（【工程建议】，非文档既有要求）。

        初版在台账已存在时**完全忽略** table_budget 参数。**现行文档里没有这条规范句**
        （README 与 PLAN-REVISION 都查过：只有"预算不足停止"这类实跑记录），
        因此这是**意外行为**而不是"违反某条要求"：命令行参数被静默忽略，
        操作者无法从产物看出预算来自哪里（3.P 证据 scenario ⑤ 复现：命令行 20→30，
        报告仍写"剩余 4 桌"）。
        现在：命令行值**更大** ⇒ 采用命令行值；**更小或缺省** ⇒ 保留台账值。
        两种情形都会由调用方打印一行说明（见 main；预算来源不允许隐式变化）。

        **"先记账后执行、不静默扩容"这条纪律不变**：台账自己从不扩容，
        扩容只能来自一次显式的命令行授权。
        """

        if not path.is_file():
            if table_budget is None:
                raise ValueError("台账不存在时必须给出 table_budget")
            return cls(table_budget=table_budget, path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        recorded = int(data["table_budget"])
        effective = recorded
        if table_budget is not None and int(table_budget) > recorded:
            effective = int(table_budget)
        return cls(table_budget=effective,
                   spent_tables=int(data["spent_tables"]),
                   rounds=list(data.get("rounds", ())),
                   consumed_root_keys=list(data.get("consumed_root_keys", ())),
                   root_sets=list(data.get("root_sets", ())),
                   path=path)


def root_statistics(per_root_deltas: Sequence[float]) -> Dict[str, Any]:
    """根级统计：点估计、根级 sd、标准误、MDE。

    **独立单位是根组**：SE = sd / sqrt(根数)。本函数不接受"桌数"作为 n，
    调用方必须先做根内平均。
    """

    n = len(per_root_deltas)
    if n < 2:
        # **不可排序**：零根或单根不构成点估计，更不得当成"均值 0"参与比较（R7-2）。
        return {"n_roots": n, "mean": (per_root_deltas[0] if n else None),
                "sd_root": None, "se_root": None, "mde": None,
                "rankable": False,
                "rankable_reason": "零有效根组" if n == 0 else "有效根组不足（<2）"}
    mean = sum(per_root_deltas) / n
    sd = statistics.stdev(per_root_deltas)
    se = sd / math.sqrt(n)
    return {"n_roots": n, "mean": round(mean, 6), "sd_root": round(sd, 6),
            "se_root": round(se, 6),
            "mde": round((Z_ALPHA_TWO_SIDED + Z_POWER_80) * se, 6),
            "rankable": True, "rankable_reason": None}


def mean_by_root(pairs: Sequence[Mapping[str, Any]]) -> List[float]:
    """把 (scenario_id, delta) 配对先做**根内平均**，再返回每根一个值。

    同一根组的多次换座是**同一抽样单位**，不得当成多个独立样本。
    """

    grouped: Dict[str, List[float]] = {}
    for item in pairs:
        grouped.setdefault(str(item["scenario_id"]), []).append(float(item["delta"]))
    return [sum(values) / len(values) for _, values in sorted(grouped.items())]


def root_set_id_of(roots: Sequence[Any]) -> str:
    """根组集合的稳定身份（R7-4）：区分"新增独立样本"与"重演"。

    **必须按 seed 取哈希，不能按 scenario_id。** 发牌由 seed 决定
    （offline/evaluate.py 用 seed 洗牌），scenario_id 只是标签。初版按标签取哈希，
    于是一个方向完全相反的错误：换 --root-prefix（标签变、牌山没变）被判"新增样本"
    照常计费；只换 --seed-base（**真换了牌山**）反被判"重演"直接拒绝。
    这条由独立对抗性复核撞出，已复现并修正。

    参数可传映射序列（取其中的 seed）或字符串序列（测试与旧调用）。
    """

    items = []
    for root in roots:
        items.append(str(root["seed"]) if isinstance(root, Mapping) else str(root))
    digest = hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()
    return "roots-" + digest[:12]


def verify_persisted_level(level: Mapping[str, Any], spec: Mapping[str, Any],
                          gate_dir: Optional[Path], repo: Path,
                          admission_corpus: Optional[Path]) -> None:
    """恢复持久化等级之前，逐候选重核**身份与准入**（REVIEW-8 R8-3）。

    为什么必须重核：持久化的 `level.candidates` 记录了"那一级当时跑的是什么"，
    但**准入是会变的**——源码依赖改动、语料更换、参数调整都会让原记录失效
    （S8-1/R7-1 的正是这个语义）。只核验命令行上的候选，等于放行一份
    **准入已被撤销**的配置。不一致一律**拒绝恢复**，不静默执行另一份配置。

    身份重算在源码变化时会自然落到同一处：`identity` 里含执行依赖指纹，
    依赖一改，记录身份与当前身份就对不上。
    """

    blocked: List[str] = []
    # 身份重算走**受监管装载**（3.P 核验发现的残留路径）：_candidate_identity 会在
    # **父进程**导入候选注册表，也就是执行**每一个**已注册候选的模块体——一个在模块体里
    # 挂住的候选会让"恢复"这条路径在拒绝之前就挂死。受监管装载在隔离子进程里完成导入与
    # 构造，身份串与父进程现算的完全一致（同一函数的同一输入）。
    gates = sibling("sitin_gates")
    for entry in level.get("candidates", ()):
        name, weights = entry.get("candidate"), entry.get("weights") or {}
        prepared = gates.supervised_prepare(name, weights)
        if not prepared.get("ok"):
            blocked.append("{0}：身份重算未完成（受监管装载失败）——{1}".format(
                name, prepared.get("reason")))
            continue
        expected = prepared["bound_identity"]
        if entry.get("identity") != expected:
            blocked.append("{0}：记录身份 {1}，当前源码/参数对应 {2}".format(
                name, entry.get("identity"), expected))
            continue
        # 准入核验必须用**上面这一份**被装载的身份，不能退回父进程现算（R7-1/R8-3）。
        admitted, detail = _gate_admits(name, weights, gate_dir, repo,
                                        admission_corpus=admission_corpus,
                                        identity=expected)
        if not admitted:
            blocked.append("{0}：{1}".format(name, detail))
    if blocked:
        raise ValueError(
            "恢复被拒绝：持久化候选未通过**当前**准入核验——" + "；".join(blocked)
            + "。请重新过门禁（记录与语料都可能已变），或换 --out/--ledger 重新开始。")


def verify_task_candidates(level: Mapping[str, Any],
                           current: Sequence[Mapping[str, Any]]) -> None:
    """第一级的持久化候选集合必须与本次命令行的候选集合**一致**（R8-3）。

    不一致说明这是**另一个任务**，不能在旧状态上继续跑：命令行的候选已经过
    本次准入核验，而真正被执行的会是持久化的那一份。
    """

    recorded = [entry.get("identity") for entry in level.get("candidates", ())]
    declared = [entry.get("identity") for entry in current]
    if recorded != declared:
        raise ValueError(
            "恢复被拒绝：持久化任务的身份与本次命令行不一致——\n"
            "  记录：{0}\n  本次：{1}\n"
            "请用与首次运行相同的候选与参数恢复，或换 --out/--ledger 显式开始新任务。".format(
                recorded, declared))


def verify_resume_identity(level: Mapping[str, Any], spec: Mapping[str, Any],
                          root_keys: Sequence[str], set_id: str) -> None:
    """恢复时必须与**记录**对账（R7-3）。

    初版恢复分支不读 level["spec"] / level["root_keys"]，一律用当前命令行，
    于是"实跑的东西"与"台账/状态里记的东西"可以不一致：换 --seats 会实跑更多桌而台账
    仍记旧的桌数，换 --root-prefix 会让台账、run_state、产物 manifest 各写一个不同的根组集合。
    这里改为**显式对账、不一致就拒绝**，而不是静默执行另一个配方。
    """

    problems = []
    if level.get("root_set_id") != set_id:
        problems.append("根组集合不同（记录 {0}，当前 {1}）".format(
            level.get("root_set_id"), set_id))
    if list(level.get("root_keys", ())) != list(root_keys):
        problems.append("根组标签不同")
    recorded = level.get("spec", {})
    for field_name in ("roots", "seats"):
        if recorded.get(field_name) != spec.get(field_name):
            problems.append("{0} 不同（记录 {1}，当前 {2}）".format(
                field_name, recorded.get(field_name), spec.get(field_name)))
    if problems:
        raise ValueError(
            "恢复被拒绝：本次命令行与已记录的执行不一致——" + "；".join(problems)
            + "。请用与首次运行相同的参数，或换 --out/--ledger 重新开始。")


def cell_dir_name(identity: str) -> str:
    """把候选身份映射成**文件系统安全**的单元目录名。

    为什么不能直接用身份串：身份形如
    `meld_opportunity_cost|adj(beta=20.0)|base(default)|src37be910e3f467d67`，
    含 `|` `(` `)` `=` `,`——这些字符在 shell、Windows 与部分归档工具下都要转义，
    按路径引用证据变成易错操作（本仓已积累 48 条这样的路径名）。
    这里做**可读 slug + 身份哈希后缀**：后缀保证单射（slug 可能因替换而碰撞），
    前缀保证人眼仍能看出是哪个候选、哪组参数、哪份源码。
    """

    slug = identity.translate(_CELL_NAME_TRANSLATION)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return "{0}-{1}".format(slug, digest)


#: 身份 → 目录名的字符替换表。
#: 括号映射为空串（只是分组记号，去掉更好读）；`|` → `__` 保留分段感。
#: 替换本身**可能碰撞**（`adj(a=1)` 与 `adj(a-1)`），单射由目录名尾部的
#: 身份哈希保证——slug 只负责可读，不负责唯一。
_CELL_NAME_TRANSLATION = str.maketrans({
    "|": "__", "(": "", ")": "", "=": "-", ",": "_",
    ":": "-", " ": "_", "/": "_", "\\": "_", "*": "_", "?": "_",
    "<": "_", ">": "_", '"': "_",
})


def candidate_manifest(candidate_name: str, weights: Mapping[str, float], repo: Path,
                       roots: Sequence[Mapping[str, Any]], spec: Mapping[str, Any],
                       ledger: BudgetLedger, *, gate_binding: Optional[Mapping] = None,
                       root_set_id: Optional[str] = None,
                       prepared: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """实验产物里的**完整候选身份 + 有效权重 + 准入依据**（REVIEW-7 S7-2 / R7-1）。

    为什么必须单独落盘：初版只有 CLI 自己的 manifest，而它的
    _effective_weights_snapshot 只解包旧装饰器，新适配器解不出来 ——
    实测 runs/sitin-2.4/.../manifest.json 里 effective_weights=null，
    既没有候选身份也没有源码指纹。**指纹存在于对象中和落进产物是两件事**。
    （CLI 侧的同类缺口已在 scripts/evaluate.py 一并修掉。）

    `gate_binding`：本次执行**依据的那条准入记录**的文件名、字节哈希与
    语料哈希。没有它，"产物 → 准入证据"这一步只能靠人工翻目录。
    """

    from dataclasses import asdict

    from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

    # **优先用受监管装载的结果**（REVIEW-9）：父进程不导入注册表、不构造候选。
    # `prepared=None` 是给单测与旧调用留的兼容路径，会真的执行候选代码，
    # 因此只在测试里出现；调度器主线一律传 prepared。
    if prepared is not None:
        params = dict(prepared.get("params") or {})
        base = dict(prepared.get("base") or {})
        source_sha = prepared.get("source_sha256")
        adjustment_identity = prepared.get("adjustment_identity")
        adjustment_spec = prepared.get("adjustment_spec")
        bound_identity = prepared["bound_identity"]
    else:
        heuristics = heuristics_registry()
        params, base = heuristics.split_declaration_params(dict(weights))
        module = heuristics.candidate_module(candidate_name)
        source_sha = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        built = heuristics.build_candidate(candidate_name, weights=weights)
        adjustment_identity = built.identity()
        adjustment_spec = {
            "name": built.adjustment.spec.name,
            "version": built.adjustment.spec.version,
            "trigger": built.adjustment.spec.trigger,
            "scope": list(built.adjustment.spec.scope),
            "bound": built.adjustment.spec.bound,
        }
        bound_identity = _candidate_identity(candidate_name, weights, repo)
    effective = asdict(DEFAULT_WEIGHTS_V1)
    effective.update(base)
    root_keys = [root["scenario_id"] for root in roots]
    return {
        "schema": "sitin-candidate-manifest/1",
        "candidate": candidate_name,
        "bound_identity": bound_identity,
        "adjustment_identity": adjustment_identity,
        "adjustment_spec": adjustment_spec,
        "effective_adjustment_params": params,
        "effective_base_weights": effective,
        "source_sha256": source_sha,
        "gate_binding": dict(gate_binding) if gate_binding is not None else None,
        "round": spec["name"],
        "roots": int(spec["roots"]),
        "seats": int(spec["seats"]),
        "root_keys": root_keys,
        # **根组身份必须按 seed 算，与台账/run_state 同一口径**（REVIEW-8 R8-5）：
        # 初版把 scenario_id 标签列表喂给 root_set_id_of，于是产物里的根组身份
        # 与 run_state 里的**永远对不上**（实测 8/8 份都不一致）。
        # 标签只是标签，发牌由 seed 决定——判重键早就按 seed 了，这里漏改了。
        "root_set_id": root_set_id or root_set_id_of(roots),
        "root_set_id_source": "verified" if root_set_id else "computed_from_seeds",
        # 目录名用**已经算出来的那份身份**（3.P 核验发现的残留路径）：_candidate_identity
        # 会在父进程导入候选注册表；而 bound_identity 在这一支里正是受监管装载给出的同一个值，
        # 也正好等于 main 实际创建单元目录时用的那个（两者必须一致，否则产物指向别处）。
        "cell_dir": cell_dir_name(bound_identity),
        "ledger_spent_tables": ledger.spent_tables,
        "note": "候选身份 = 模块 + 有效参数 + 源码指纹；bound_identity 与门禁记录可互核",
    }


@dataclass
class RunState:
    """分级执行的持久化状态（REVIEW-7 R7-3）。

    为什么必须有：初版 main 永远只跑第一轮，然后用**临时构造**的根标签
    "规划"第二轮就退出——没有等级状态、没有存活集合、没有恢复入口。
    "能在预算内跑完一轮"因此**不等于**"支持分级评估"。
    """

    path: Path
    levels: List[Dict[str, Any]] = field(default_factory=list)
    cursor_level: int = 0
    stop_reason: Optional[str] = None

    @classmethod
    def load(cls, path: Path) -> "RunState":
        if not path.is_file():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(path=path,
                   levels=list(data.get("levels", ())),
                   cursor_level=int(data.get("cursor_level", 0)),
                   stop_reason=data.get("stop_reason"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"schema": RUN_STATE_SCHEMA, "levels": self.levels,
             "cursor_level": self.cursor_level, "stop_reason": self.stop_reason},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def plan_round(ledger: BudgetLedger, survivors: Sequence[str], spec: Mapping[str, Any],
               root_keys: Sequence[str]) -> Dict[str, Any]:
    """决定下一轮是跑还是停；**只看预算，不静默扩容**。"""

    tables = spec["roots"] * spec["seats"] * 2 * len(survivors)
    if not survivors:
        return {"decision": "stop", "round": spec["name"], "reason": "没有存活候选"}
    if not ledger.can_afford(tables):
        # 停止点必须带上轮次名，否则无法回答"卡在哪一轮"。
        return {"decision": "stop", "round": spec["name"],
                "reason": "预算不足：本轮需 {0} 桌，剩余 {1} 桌".format(
                    tables, ledger.remaining_tables),
                "required_tables": tables,
                "remaining_tables": ledger.remaining_tables}
    if spec["roots"] > len(root_keys):
        return {"decision": "stop", "round": spec["name"],
                "reason": "根组不足：本轮需 {0} 根，可用 {1} 根".format(
                    spec["roots"], len(root_keys))}
    return {"decision": "run", "tables": tables, "round": spec["name"],
            "candidates": list(survivors), "roots": spec["roots"],
            "seats": spec["seats"]}


def select_survivors(results: Mapping[str, Mapping[str, Any]],
                     keep_fraction: float) -> List[str]:
    """按根级点估计保留前若干名。

    **本函数只做开发期预算分配**：不声称被淘汰者"统计上明确变坏"，
    也不因为区间跨零就保留全部——那会让预算失去意义（README §6.2 边界）。
    淘汰依据是点估计，因此**结果不得当作效果证据**。
    """

    # **只对可排序的候选排序**：初版用 `mean or 0.0`，于是"零有效根组"的失败候选
    # 被当成均值 0，**反而胜过有效均值 −1 的候选**（R7-2）。缺失值一律不得补零。
    rankable = {name: stats for name, stats in results.items()
                if stats.get("rankable") and stats.get("mean") is not None}
    unrankable = sorted(set(results) - set(rankable))
    if not rankable:
        return []
    ranked = sorted(rankable.items(), key=lambda kv: (-kv[1]["mean"], kv[0]))
    keep = max(1, int(math.ceil(len(ranked) * keep_fraction)))
    return [name for name, _ in ranked[:keep]]


def sibling(name: str):
    """按名加载同目录工具模块（只加载一次）。

    `sitin_gates` 与 `sitin_process` 都在本目录下、不是包成员，
    因此用 importlib 显式装载；缓存避免每次调用都重新 exec 一遍。
    """

    cached = _SIBLINGS.get(name)
    if cached is not None:
        return cached
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location(name, _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / (name + ".py")))
    module = _ilu.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    _SIBLINGS[name] = module
    return module


#: 同目录工具模块的加载缓存。
_SIBLINGS: Dict[str, Any] = {}


def _candidate_identity(name: str, weights: Mapping[str, float], repo: Path) -> str:
    """候选的**完整身份**：模块 + 有效参数 + **执行依赖指纹**（R7-5/R7-1/S8-1）。

    与门禁侧**共用同一个函数**（`sitin_gates.candidate_identity`），
    否则"门禁通过的那份配置"与"实际被调度的配置"可能对不上而无人察觉。
    指纹取自 import 依赖闭包（见 `offline/scoring_sources.py`），
    因此**被依赖文件的改动也会让身份变化**——初版只对入口文件取指纹，
    改一个被 import 的模块不会让旧记录失效（REVIEW-8 S8-1）。
    """

    return sibling("sitin_gates").candidate_identity(name, weights)


def _corpus_sha256(path: Optional[Path]) -> Optional[str]:
    """准入语料的**内容哈希**；未声明或读不到时返回 None（fail-closed）。"""

    if path is None:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _scan_gate_records(identity: str, directory: Path) -> Dict[str, Any]:
    """扫描门禁记录目录，按绑定身份与**证据种类**分桶。

    **fail-closed**（2026-09-15 独立复核撞出）：初版对缺 `evidence_kind` 的记录
    按 admission 处理，而本次事故的形态恰恰就是"没有证据种类字段的记录"。
    缺字段/未知值一律**不作准入依据**；但与"没有匹配记录"要给**可区分**的理由，
    否则排查时看不出是记录格式问题还是根本没有记录。
    """

    import json as _json

    admission: List[Dict[str, Any]] = []
    unknown_kind = 0
    for record_path in sorted(directory.glob("*.json")):
        try:
            data = _json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, Mapping):
            continue
        if data.get("bound_identity") != identity:
            continue
        if data.get("evidence_kind") != "admission":
            if data.get("evidence_kind") is None:
                unknown_kind += 1
            continue
        admission.append({
            "name": record_path.name,
            "sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
            "data": data,
        })
    return {"admission": admission, "unknown_kind": unknown_kind}


def _gate_admits(name: str, weights: Mapping[str, float],
                 gate_dir: Optional[Path], repo: Path, *,
                 admission_corpus: Optional[Path] = None,
                 identity: Optional[str] = None) -> Tuple[bool, str]:
    """核验存在**绑定身份一致、语料一致且 admitted=True** 的门禁记录（REVIEW-7 R7-1）。

    初版 `main` 直接 `reserve → run_round`，**从不检查门禁**：
    连 `adj.beta=0`（等价基线）这种按 G-2 应被拦的配置也能扣预算并执行。
    本函数把"通过记录"变成执行的**前置条件**；参数或源码一改，身份即变，原记录自动失效。

    **语料维度（R7-1 剩余项）**：身份里**不含语料**，于是"在某份语料上过了 G-2"
    这条结论可以被任意换语料后的运行沿用——而触发面、改选率都随语料变
    （价值族② 的实测就是一份没有链状态窗口的语料）。因此：
      - 调用方必须显式声明本次准入所依据的语料（`admission_corpus`）；
      - 记录必须带 `corpus.sha256`，且与声明语料的**字节哈希**一致；
      - 旧格式记录（无 `corpus.sha256`）一律**拒绝**，并给出可区分的理由。
    """

    if gate_dir is None:
        return False, "未提供门禁记录目录：按 R7-1 不允许在无通过记录时扣预算"
    corpus_sha = _corpus_sha256(admission_corpus)
    if corpus_sha is None:
        return False, ("未声明准入语料（--admission-corpus）或该文件不可读："
                       "按 R7-1 不允许在语料身份不明时扣预算")
    # 身份优先用**受监管装载**给出的值（REVIEW-9）：父进程因此不必导入候选注册表。
    identity = identity or _candidate_identity(name, weights, repo)
    directory = Path(gate_dir)
    if not directory.is_dir():
        return False, "门禁记录目录不存在：{0}".format(directory)
    scanned = _scan_gate_records(identity, directory)
    bound = scanned["admission"]
    if not bound:
        if scanned["unknown_kind"]:
            return False, (
                "找到 {0} 条**绑定身份一致但缺 evidence_kind 字段**的记录：不作为准入依据。"
                "请用当前 sitin_gates.py 重新产出准入记录。").format(scanned["unknown_kind"])
        return False, "没有与当前候选**绑定身份一致**的门禁记录：{0}".format(identity)
    # 语料维度：先按语料筛，再判结论。两类失败给不同理由。
    stale = [item["name"] for item in bound
             if not isinstance(item["data"].get("corpus"), Mapping)
             or item["data"]["corpus"].get("sha256") is None]
    if stale and len(stale) == len(bound):
        return False, (
            "绑定身份一致的 {0} 条记录都**没有语料指纹**（旧格式）：不作为准入依据。"
            "请用当前 sitin_gates.py 重新产出准入记录。").format(len(stale))
    matches = [item for item in bound
               if isinstance(item["data"].get("corpus"), Mapping)
               and item["data"]["corpus"].get("sha256") == corpus_sha]
    if not matches:
        recorded = sorted({str(item["data"].get("corpus", {}).get("sha256"))
                           for item in bound})
        return False, (
            "准入语料不一致：当前声明 {0}，记录里的语料指纹为 {1}。"
            "语料变了，原准入结论就不再适用于本次执行（R7-1）。").format(
            corpus_sha, recorded)
    # **多条记录必须一致**（2026-09-15 独立复核撞出）：初版按文件名取**首个**匹配即返回，
    # 于是同一身份存在旧 PASS + 新 FAIL 两条记录时，判定取决于文件名字典序。
    # 有分歧就拒绝，不猜。
    verdicts = {bool(item["data"].get("admitted")) for item in matches}
    if len(verdicts) > 1:
        return False, ("同一绑定身份、同一语料存在 {0} 条**结论不一致**的门禁记录：{1}；"
                       "按 fail-closed 拒绝执行，请清理旧记录。").format(
            len(matches), sorted(item["name"] for item in matches))
    if not next(iter(verdicts)):
        first = matches[0]["data"]
        detail = first.get("failed") or first.get("insufficient") or []
        if len(matches) > 1:
            detail = "{0}（{1} 条记录结论一致）".format(detail, len(matches))
        return False, "门禁未通过（admitted=false）：{0}".format(detail)
    return True, identity


def gate_binding(name: str, weights: Mapping[str, float], gate_dir: Optional[Path],
                 repo: Path, admission_corpus: Optional[Path], *,
                 identity: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """本次准入**依据的那条记录**的可核验摘要；用于写进候选产物。

    没有它，"产物 → 准入证据"只能靠人工翻目录；有了它，
    产物里就写着"依据的是哪个文件、那个文件的哈希、以及当时用的语料哈希"。
    """

    if gate_dir is None:
        return None
    directory = Path(gate_dir)
    if not directory.is_dir():
        return None
    corpus_sha = _corpus_sha256(admission_corpus)
    identity = identity or _candidate_identity(name, weights, repo)
    for item in _scan_gate_records(identity, directory)["admission"]:
        data = item["data"]
        corpus = data.get("corpus")
        if not isinstance(corpus, Mapping) or corpus.get("sha256") != corpus_sha:
            continue
        if not bool(data.get("admitted")):
            continue
        return {
            "record": item["name"],
            "record_sha256": item["sha256"],
            "corpus_sha256": corpus_sha,
            "corpus_path": corpus.get("path"),
            "evidence_kind": "admission",
        }
    return None


def read_pairs(results_path: Path, baseline_id: str,
               challenger_id: str) -> List[Dict[str, Any]]:
    """从 results.jsonl 读出 (scenario_id, perm, delta) —— 被测座位的配对差。

    被测座位由 `policy_ids_by_seat` 反查；两臂同 `(scenario_id, pair_id)` 配对。
    """

    rows = [json.loads(line) for line in Path(results_path).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    by_pair: Dict[Tuple[str, str], Dict[str, float]] = {}
    for row in rows:
        if row.get("status") != "complete":
            continue
        policy_ids = row.get("policy_ids_by_seat") or []
        scores = row.get("scores_after") or []
        arm = row["result_id"].rsplit(":", 1)[-1]
        if arm not in (baseline_id, challenger_id):
            continue
        seats = [i for i, item in enumerate(policy_ids) if item == arm]
        if len(seats) != 1 or seats[0] >= len(scores):
            continue
        key = (str(row.get("scenario_id")), str(row.get("pair_id")))
        by_pair.setdefault(key, {})[arm] = float(scores[seats[0]])
    pairs = []
    for (scenario_id, pair_id), arms in sorted(by_pair.items()):
        if baseline_id in arms and challenger_id in arms:
            pairs.append({"scenario_id": scenario_id, "pair_id": pair_id,
                          "delta": arms[challenger_id] - arms[baseline_id]})
    return pairs


#: 与 `run_round` 写入 experiment.json 的换座顺序**必须一致**（顺序参与 pair_id）。
PLANNED_PERMUTATIONS: Tuple[Tuple[int, ...], ...] = (
    (0, 1, 2, 3), (1, 2, 3, 0), (2, 3, 0, 1), (3, 0, 1, 2),
)


def run_round(candidate_name: str, weights: Mapping[str, float], roots: Sequence[Mapping[str, Any]],
              seats: int, out_dir: Path, *, repo: Path, baseline_id: str = "weighted_heuristic_v2",
              ruleset: str = "hangma-mvp-v10-public-counts",
              timeout_sec: Optional[float] = None) -> List[Dict[str, Any]]:
    """跑一轮：调用**生产 CLI**（与 A10 验证过的同一条路径），返回配对差。

    用 CLI 而不是自己装配，是为了让调度器与"人工跑一轮"走完全相同的链路。

    **可终止（REVIEW-7 2.5 剩余项）**：初版用 `subprocess.run(check=True)`，
    **没有超时**——本路线跑的恰恰是"离线生成的任意候选代码"，一个死循环
    就能把整个调度器挂住且不留任何产物。这里改为可超时、可杀进程组的执行，
    失败以 `RoundFailed` 显式抛出，由调用方按 R7-2 记为**不可排序**。
    """

    # 换座顺序**参与 pair_id**，因此必须与 `PLANNED_PERMUTATIONS` 同源——
    # 计划核验（R8-4）用它反推"计划里应该有哪几对"。
    permutations = [list(item) for item in PLANNED_PERMUTATIONS[:seats]]
    challenger_id = "cand_" + candidate_name
    experiment = {
        "experiment_schema_version": 1, "kind": "matches", "clock_mode": "logical",
        "baseline_policy": {"policy_id": baseline_id, "name": baseline_id, "weights": {}},
        "challenger_policy": {"policy_id": challenger_id, "name": candidate_name,
                              "weights": dict(weights)},
        "opponent_pool": [{"policy_id": "opp-{0}".format(i), "name": baseline_id,
                           "weights": {}} for i in range(3)],
        "tournament_config": {
            "schema_version": 1, "max_games": 1, "rounds_per_game": 8,
            "rules": {"ruleset_version": ruleset, "base_score": 1, "you_cai_bi_kao": False},
            "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 1.0,
                       "discard_timeout_sec": 3.0}},
        "seeds": [dict(root) for root in roots],
        "seat_permutations": permutations,
        "initial_dealer": 0, "initial_scores": [0, 0, 0, 0],
        "match_id_prefix": "sitin-sched", "primary_metric": "table_score_delta",
        "tie_method": "strict", "n_resamples": 200, "resample_seed": 2029,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    experiment_path = out_dir / "experiment.json"
    experiment_path.write_text(json.dumps(experiment, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    command = [
        str(repo / ".venv/bin/python"), str(repo / "scripts/evaluate.py"), "matches",
        "--experiment", str(experiment_path), "--out", str(out_dir / "out"),
    ]
    # `is not None` 而不是真值判断：0 是合法的"立刻到期"。
    limit = float(timeout_sec) if timeout_sec is not None else round_timeout_sec(
        int(len(roots)) * seats * 2)
    result = _run_cli(command, repo, limit)
    if result.timed_out:
        raise RoundFailed(
            "运行超时：{0} 秒内未结束（已终止进程组，信号 {1}）".format(
                limit, "+".join(result.signals_sent) or "无"),
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            timeout_sec=limit, supervision=result.to_json())
    if result.returncode != 0:
        raise RoundFailed(
            "评估 CLI 非零退出：returncode={0}".format(result.returncode),
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            timeout_sec=limit, supervision=result.to_json())
    # **对照计划核验结果矩阵**（REVIEW-8 R8-4）：不足或不完整一律判本轮失败，
    # 绝不让"恰好在某些输入上成功的那些行"单独去参与排名。
    verdict = verify_round_plan(out_dir / "out/results.jsonl", roots, seats,
                                baseline_id, challenger_id)
    if not verdict["ok"]:
        raise RoundFailed(
            "结果矩阵与计划不符：" + "；".join(verdict["problems"]),
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            timeout_sec=limit, supervision=result.to_json(),
            problems=verdict["problems"])
    return read_pairs(out_dir / "out/results.jsonl", baseline_id, challenger_id)


def verify_round_plan(results_path: Path, roots: Sequence[Mapping[str, Any]], seats: int,
                      baseline_id: str, challenger_id: str) -> Dict[str, Any]:
    """对照**计划**核验本轮桌赛结果矩阵（REVIEW-8 R8-4）。

    初版只把非 complete 行丢掉、再看剩下够不够 2 根就算了。于是一个候选只要在
    **部分输入上执行失败**，剩下的成功行照样参与排名：实测 4 根 × 2 换座 × 2 臂
    = 16 条里每根有一条候选臂 error，8 个配对只剩 4 个，仍得到
    `rankable=true`、均值 +100、SE=0，**并晋级**。这等于按"候选是否恰好在某些
    输入上成功"来筛样本——失败候选反而拿到偏高评分。

    本函数逐项核对：总行数 = 根 × 换座 × **双臂**；每行 `status=complete`；
    计划中的每个 `(根, 换座)` 恰好各有基线与候选两行且被测座位可定位。
    任何不符都进 `problems`，由调用方判**不可排序**。

    **边界**：本版不接受"与候选无关的环境排除"。若将来确需排除，必须先**预先登记**
    排除口径与配对处理规则，并显式记录原因；不得靠把异常行删掉了事。
    """

    rows = [json.loads(line) for line in Path(results_path).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    expected_pairs = len(roots) * int(seats)
    expected_tables = expected_pairs * 2
    problems: List[str] = []
    status_counts: Dict[str, int] = {}
    for row in rows:
        status = str(row.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    if len(rows) != expected_tables:
        problems.append("结果行数 {0}，计划应为 {1}".format(len(rows), expected_tables))
    broken = sorted(s for s in status_counts if s != "complete")
    if broken:
        problems.append("存在非 complete 结果：{0}".format(
            {s: status_counts[s] for s in broken}))
    by_pair: Dict[Tuple[str, Tuple[int, ...]], Dict[str, Any]] = {}
    for row in rows:
        permutation = row.get("seat_permutation")
        if not isinstance(permutation, (list, tuple)):
            # 兜底：pair_id 的冒号后缀就是换座数字（形如 "<scenario>:0123"）。
            suffix = str(row.get("pair_id", "")).split(":")[-1]
            permutation = tuple(int(ch) for ch in suffix if ch.isdigit())
        key = (str(row.get("scenario_id")), tuple(int(item) for item in permutation))
        arms = by_pair.setdefault(key, {"baseline": 0, "challenger": 0, "other": 0})
        policy_ids = row.get("policy_ids_by_seat") or []
        # 每行**恰好**属于一臂：被测座位上是基线或候选，其余三个座位是对手。
        if policy_ids.count(baseline_id) == 1:
            arms["baseline"] += 1
        elif policy_ids.count(challenger_id) == 1:
            arms["challenger"] += 1
        else:
            arms["other"] += 1
    # 计划的键用**换座元组**而不是 pair_id 字符串：pair_id 的拼法由评估驱动决定，
    # 不能让它成为计划核验的隐含依赖。
    planned = {
        (str(root["scenario_id"]), PLANNED_PERMUTATIONS[index])
        for root in roots for index in range(int(seats))
    }
    missing = sorted(key for key in planned if key not in by_pair)
    if missing:
        problems.append("{0} 个计划的（根, 换座）没有任何结果；示例 {1}".format(
            len(missing), ["{0}/{1}".format(key[0], "".join(map(str, key[1])))
                           for key in missing[:3]]))
    incomplete = sorted(
        "{0}/{1}".format(key[0], "".join(map(str, key[1])))
        for key, arms in by_pair.items()
        if arms["baseline"] != 1 or arms["challenger"] != 1 or arms["other"])
    if incomplete:
        problems.append("{0} 个配对不是「基线一臂 + 候选一臂」；示例 {1}".format(
            len(incomplete), incomplete[:3]))
    return {
        "ok": not problems,
        "problems": problems,
        "expected_tables": expected_tables,
        "rows": len(rows),
        "status_counts": status_counts,
        "expected_pairs": expected_pairs,
        "pairs_observed": len(by_pair),
    }


def _run_cli(command: Sequence[str], cwd: Path, timeout_sec: float):
    """跑外部命令并**保证可终止**；返回 `sitin_process.SupervisedResult`。

    **与门禁共用同一个受监管入口**（REVIEW-8 S8-2）：初版这里只等待**直接子进程**——
    组长收到 TERM 后退出、而后代忽略 TERM 时，`process.poll() is None` 为假，
    于是**不进入发 KILL 的分支**，随后无超时的 `communicate()` 继续等后代持有的管道；
    实测配置超时 0.5 秒、宽限 5 秒，**8.041 秒**后才返回，且输出写着后代是
    `CHILD_NATURAL_EXIT`（自然退出，不是被杀的）。两处各写一份终止逻辑就会有两份缺陷，
    因此收敛到 `sitin_process.run_supervised`。
    """

    return sibling("sitin_process").run_supervised(
        command, cwd=cwd, timeout_sec=timeout_sec, grace_sec=_TERMINATE_GRACE_SEC)


def _md_cell(text: Any) -> str:
    """Markdown 表格单元格转义。

    候选身份里含 `|`（分段符），直接写进表格会被解析成列分隔符——
    报告一旦渲染错列，读的人会以为台账记了别的东西（根 AGENTS.md §8）。
    """

    return str(text).replace("|", "\\|").replace("\n", " ")


def render(ledger: BudgetLedger, report: Mapping[str, Any]) -> str:
    lines = ["# 坐隐 2.4 顺序淘汰调度", "",
             "**淘汰只作开发期预算分配，不构成效果证据**（README §6.2 边界）。", "",
             "## 预算台账（独立于日志）", "",
             "| 项 | 值 |", "| --- | ---: |",
             "| 预算（桌） | {0} |".format(ledger.table_budget),
             "| 已用（桌） | {0} |".format(ledger.spent_tables),
             "| 剩余（桌） | {0} |".format(ledger.remaining_tables), "",
             "## 轮次", "", "| 轮次 | 候选 | 根组 | 换座 | 桌 |", "| --- | --- | ---: | ---: | ---: |"]
    for item in ledger.rounds:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            _md_cell(item["round"]), _md_cell("、".join(item["candidates"])),
            item["roots"], item["seats"], item["tables"]))
    lines += ["", "## 每候选根级统计", "",
              "不可排序的候选（运行失败 / 零有效根组）**不参与点估计排序**，",
              "也不得把缺失值补零（REVIEW-7 R7-2）。", "",
              "| 候选 | 根数 | 根级点估计 | 根级 sd | SE | MDE | 状态 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for name, stats in sorted(report.get("candidates", {}).items()):
        status = "可排序" if stats.get("rankable") else "不可排序：{0}".format(
            stats.get("rankable_reason") or "证据不足")
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
            _md_cell(name), stats.get("n_roots"), stats.get("mean"),
            stats.get("sd_root"), stats.get("se_root"), stats.get("mde"),
            _md_cell(status)))
    if report.get("stop_reason"):
        lines += ["", "## 停止", "", report["stop_reason"]]
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """分级顺序淘汰：**先记账后执行**，到预算即停，可中断恢复（R7-3）。"""

    ap = argparse.ArgumentParser(description="坐隐 2.4 顺序淘汰调度器（分级 + 恢复）")
    ap.add_argument("--candidate", action="append", required=True,
                    help="候选名，可重复")
    ap.add_argument("--weights", action="append", default=[],
                    help="与 --candidate 一一对应的 JSON；缺省为 {}")
    ap.add_argument("--seed-base", type=int, default=2026092000)
    ap.add_argument("--root-prefix", default="scale-")
    ap.add_argument("--root-count", type=int, default=4)
    ap.add_argument("--seats", type=int, default=1)
    ap.add_argument("--budget-tables", type=int, default=20)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate-records", required=True,
                    help="门禁通过记录目录；按 R7-1 必须核验后才允许扣预算")
    ap.add_argument("--admission-corpus", required=True,
                    help="准入证据所依据的**决策语料**路径；记录里的语料指纹必须与它一致。"
                         "身份里不含语料，因此不声明语料就无法判定记录是否仍适用（R7-1）")
    ap.add_argument("--round-timeout-sec", type=float, default=None,
                    help="单轮评估墙钟上限（秒）；缺省按桌数自动给出（REVIEW-7 2.5）")
    ap.add_argument("--levels", default=None,
                    help="分级配方 JSON 数组；每项 {name,roots,seats,keep_fraction}。"
                         "缺省用 ROUND_SPECS，并用 --root-count/--seats 覆盖第一级")
    ap.add_argument("--allow-rerun", action="store_true",
                    help="允许在已消费的（轮次, 根组集合）上重演：照常计费并标记 rerun")
    args = ap.parse_args(argv)

    repo = Path(__file__).resolve().parents[3]
    # 预算来源必须**可见**（3.P 编排验证）：台账里的预算才是账，命令行只允许追加。
    ledger_path = Path(args.ledger)
    recorded_budget = None
    if ledger_path.is_file():
        recorded_budget = int(json.loads(
            ledger_path.read_text(encoding="utf-8"))["table_budget"])
    ledger = BudgetLedger.load(ledger_path, table_budget=args.budget_tables)
    if recorded_budget is not None and ledger.table_budget != recorded_budget:
        print("预算：台账原记 {0} 桌 ⇒ 本次生效 {1} 桌（命令行 {2} 桌；只允许追加，不缩减）".format(
            recorded_budget, ledger.table_budget, args.budget_tables))
    elif recorded_budget is not None and args.budget_tables < recorded_budget:
        print("预算：命令行 {0} 桌小于台账 {1} 桌，按台账值继续（不缩减已授权预算）".format(
            args.budget_tables, ledger.table_budget))
    weights_list = list(args.weights) + ["{}"] * (len(args.candidate) - len(args.weights))
    candidates = list(zip(args.candidate, [json.loads(w) for w in weights_list]))

    if args.levels:
        specs = [dict(item) for item in json.loads(args.levels)]
    else:
        specs = [dict(item) for item in ROUND_SPECS]
        specs[0]["roots"] = args.root_count
        specs[0]["seats"] = args.seats

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = RunState.load(out_dir / "run_state.json")
    # 每次运行都**重算**停止原因：初版从不清除，于是"预算不足停止后追加预算重跑"
    # （工程期望；现行文档未写成规范句）的报告里仍写着上一次的停止原因——
    # 报告说停止、实际已执行并扣款，这本身与是否追加预算无关，是**报告失真**。
    state.stop_reason = None

    # R7-1：**先核验门禁，再扣预算**。不通过就根本不进入评估驱动。
    # 核验包含**语料**：身份里不含语料，因此必须显式声明并逐字节比对。
    gate_dir = Path(args.gate_records)
    admission_corpus = Path(args.admission_corpus)
    gates = sibling("sitin_gates")
    blocked: List[str] = []
    prepared_by_identity: Dict[str, Dict[str, Any]] = {}
    survivors: List[Dict[str, Any]] = []
    for name, weights in candidates:
        # **① 装载与构造先过受监管入口**（REVIEW-9）：注册表导入、候选模块体与
        # 按参数构造都是候选作者写的代码。父进程一旦自己导入/构造，就会在
        # "还没拒绝"的时候被候选挂死——那就等于把可终止性交给了候选。
        prepared = gates.supervised_prepare(name, weights)
        if not prepared.get("ok"):
            blocked.append("{0}：装载/构造未完成——{1}".format(name, prepared.get("reason")))
            continue
        identity = prepared["bound_identity"]
        # **② 再核验准入**（R7-1/R8-3），用的正是①这份被装载的身份。
        admitted, detail = _gate_admits(name, weights, gate_dir, repo,
                                        admission_corpus=admission_corpus,
                                        identity=identity)
        if not admitted:
            blocked.append("{0}：{1}".format(name, detail))
            continue
        prepared_by_identity[identity] = dict(prepared)
        survivors.append({
            "candidate": name, "weights": dict(weights), "identity": identity,
            "gate_binding": gate_binding(name, weights, gate_dir, repo,
                                         admission_corpus, identity=identity)})
    if blocked:
        print("拒绝进入评估队列（装载/构造或门禁未通过）：")
        for item in blocked:
            print("  ! {0}".format(item))
        return 1

    offset = 0
    for index, spec in enumerate(specs):
        root_specs = [{"seed": args.seed_base + offset + i,
                       "scenario_id": "{0}L{1}-{2}".format(args.root_prefix, index + 1, i)}
                      for i in range(int(spec["roots"]))]
        root_keys = [root["scenario_id"] for root in root_specs]
        set_id = root_set_id_of(root_specs)
        offset += int(spec["roots"])

        level = state.levels[index] if index < len(state.levels) else None
        # **恢复前核对完整任务身份与准入**（REVIEW-8 R8-3）：初版只核验"本次命令行
        # 的候选"，随后恢复分支就换回持久化的 `level.candidates`——于是命令行上
        # 已通过准入的 β=40 与持久化的、**准入已被撤销**的 β=20 可以不同，
        # 实际执行并晋级的仍是 β=20，退出码还写 0。已完成的等级还会直接复用旧幸存者。
        if level is not None:
            verify_persisted_level(level, spec, gate_dir, repo, admission_corpus)
            if index == 0:
                verify_task_candidates(level, survivors)
        if index < state.cursor_level:
            survivors = [dict(entry) for entry in level.get("survivors", ())]
            continue
        if not survivors:
            state.stop_reason = "{0}：没有存活候选".format(spec["name"])
            state.save()
            break

        if level is None:
            # 台账可能已经为这一级扣过款、而状态没来得及落盘（reserve 先落盘，
            # state.save 在其后）。此时按台账**重建**该级，而不是重新 reserve——
            # 重来一次要么被判"重演"抛错，要么在 --allow-rerun 下重复扣款。
            reserved = next((item for item in ledger.root_sets
                             if item.get("round") == spec["name"]
                             and item.get("root_set_id") == set_id), None)
            if reserved is not None:
                by_identity = {entry["identity"]: entry for entry in survivors}
                recorded_ids = list(reserved.get("candidates", ()))
                missing = [item for item in recorded_ids if item not in by_identity]
                if missing:
                    raise ValueError(
                        "台账已为 {0} 预留预算，但当前候选集合与记录不一致：{1}".format(
                            spec["name"], missing))
                level = {"round": spec["name"], "spec": dict(spec),
                         "root_keys": list(reserved.get("root_keys", root_keys)),
                         "root_specs": [dict(root) for root in root_specs],
                         "root_set_id": set_id,
                         "candidates": [dict(by_identity[item]) for item in recorded_ids],
                         "results": {}, "done": [], "survivors": [],
                         "reconciled_from_ledger": True}
                state.levels.append(level)
                state.save()
                print("恢复：{0} 台账已有预留而状态缺失，按台账重建该级（不重复扣款）".format(
                    spec["name"]))
            else:
                decision = plan_round(ledger, [e["identity"] for e in survivors],
                                      spec, root_keys)
                if decision["decision"] == "stop":
                    state.stop_reason = "{0}：{1}".format(spec["name"], decision["reason"])
                    state.save()
                    print("停止：{0}".format(state.stop_reason))
                    break
                ledger.reserve(spec["name"], [e["identity"] for e in survivors],
                               int(spec["roots"]), int(spec["seats"]), root_keys,
                               root_set_id_value=set_id, allow_rerun=args.allow_rerun)
                level = {"round": spec["name"], "spec": dict(spec),
                         "root_keys": root_keys,
                         "root_specs": [dict(root) for root in root_specs],
                         "root_set_id": set_id,
                         "candidates": [dict(e) for e in survivors],
                         "results": {}, "done": [], "survivors": []}
                state.levels.append(level)
                state.save()
        else:
            # **恢复必须与记录对账**：初版一律取当前命令行，于是换 --seats / --root-prefix
            # 恢复会让"实跑的"与"台账/状态/产物里记的"三份不一致。
            verify_resume_identity(level, spec, root_keys, set_id)
            spec = dict(level["spec"])
            root_specs = [dict(root) for root in level["root_specs"]]
            root_keys = list(level["root_keys"])
            # **无条件**打印恢复证据：初版只在 done 非空时打印，于是"预算已预留、候选一个都没跑"这种中断（正是本步要证的情形）反而没有落盘证据。
            print("恢复：{0} 预算已预留，不重复扣款；已完成 {1}/{2}".format(
                spec["name"], len(level["done"]), len(level["candidates"])))

        survivors = [dict(entry) for entry in level["candidates"]]
        for entry in level["candidates"]:
            identity = entry["identity"]
            if identity in level["done"]:
                continue                      # 缓存复用：不重复扣预算、不重复执行
            name, weights = entry["candidate"], entry["weights"]
            # 目录名走**文件系统安全 slug + 身份哈希**：身份串含 | ( ) = ,
            # 直接当路径名要转义（REVIEW-7 阶段二复核的次要清理项）。
            cell = out_dir / spec["name"] / cell_dir_name(identity)
            cell.mkdir(parents=True, exist_ok=True)
            try:
                pairs = run_round(name, weights, root_specs, int(spec["seats"]),
                                  cell, repo=repo, timeout_sec=args.round_timeout_sec)
            except RoundFailed as failure:
                # **失败不静默**（R7-2）：记为不可排序、落盘失败证据、继续下一个候选。
                # 已预留的预算不退——台账是"先记账后执行"，退预算会让"到预算即停"失效。
                level["results"][identity] = {
                    "n_roots": 0, "mean": None, "sd_root": None, "se_root": None,
                    "mde": None, "rankable": False,
                    "rankable_reason": "本轮运行失败：{0}".format(failure),
                    "candidate": name, "weights": weights, "pairs": 0,
                    "status": "failed",
                }
                (cell / "failure.json").write_text(
                    json.dumps(failure.to_json(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                level["done"].append(identity)
                state.save()
                print("候选 {0} 本轮未产出可用结果：{1}".format(name, failure))
                if failure.stderr.strip():
                    print("  ! stderr 尾部：{0}".format(
                        failure.stderr.strip().splitlines()[-1][:200]))
                continue
            stats = root_statistics(mean_by_root(pairs))
            level["results"][identity] = dict(
                stats, candidate=name, weights=weights, pairs=len(pairs))
            (cell / "candidate-manifest.json").write_text(
                json.dumps(candidate_manifest(
                    name, weights, repo, root_specs, spec, ledger,
                    gate_binding=entry.get("gate_binding"), root_set_id=set_id,
                    prepared=prepared_by_identity.get(identity)),
                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            level["done"].append(identity)
            state.save()                      # 每完成一个候选就落盘 ⇒ 中断可恢复

        keep = set(select_survivors(level["results"], float(spec["keep_fraction"])))
        level["survivors"] = [dict(entry) for entry in level["candidates"]
                              if entry["identity"] in keep]
        state.cursor_level = index + 1
        state.save()
        survivors = [dict(entry) for entry in level["survivors"]]
        if not survivors:
            failed_now = sorted(
                stats["candidate"] for stats in level["results"].values()
                if stats.get("status") == "failed")
            reason = "零有效根组或全部不可排序，无候选晋级"
            if failed_now:
                reason = "本轮有候选运行失败（{0}）；{1}".format(
                    "、".join(failed_now), reason)
            state.stop_reason = "{0}：{1}".format(spec["name"], reason)
            state.save()
            break

    report: Dict[str, Any] = {"schema": SCHEMA, "levels": state.levels,
                              "candidates": {}}
    for level in state.levels:
        report["candidates"].update(level.get("results", {}))
    if state.stop_reason:
        report["stop_reason"] = state.stop_reason
    (out_dir / "elimination.json").write_text(
        json.dumps({"ledger": ledger.to_json(), "report": report, "run_state": {
            "cursor_level": state.cursor_level, "stop_reason": state.stop_reason}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "elimination.md").write_text(render(ledger, report) + (
        "\n## 分级执行\n\n{0}\n".format(
            state.stop_reason or "已跑到配方末级；cursor_level={0}".format(state.cursor_level))),
        encoding="utf-8")
    print(render(ledger, report))
    return 0 if state.stop_reason is None or state.cursor_level >= len(specs) else 1


def find_stop(ledger: BudgetLedger, survivors: Sequence[str],
              specs: Sequence[Mapping[str, Any]],
              root_keys: Sequence[str]) -> Dict[str, Any]:
    """按配方逐轮推演，返回**第一个跑不动的地方**——用于"到预算即停"的可测性。"""

    # R7-7：初版每轮都对**同一个初始余额**调用 plan_round，于是
    # "第一轮 128 + 第二轮 512 = 640 > 预算 600" 会被报告为"全部可完成"。
    # 修法：在**临时余额**上累计扣款，不动真实台账。
    current = list(survivors)
    remaining = ledger.remaining_tables
    for spec in specs:
        tables = spec["roots"] * spec["seats"] * 2 * len(current)
        if current and tables > remaining:
            return {"decision": "stop", "round": spec["name"],
                    "reason": "预算不足（累计口径）：本轮需 {0} 桌，累计剩余 {1} 桌".format(
                        tables, remaining),
                    "required_tables": tables, "remaining_tables": remaining}
        decision = plan_round(ledger, current, spec, root_keys)
        if decision["decision"] == "stop":
            return decision
        remaining -= tables
        current = current[:max(1, int(math.ceil(len(current) * spec["keep_fraction"])))]
    return {"decision": "run", "round": "全部轮次均可在预算内完成",
            "remaining_after_all": remaining}


if __name__ == "__main__":
    raise SystemExit(main())
