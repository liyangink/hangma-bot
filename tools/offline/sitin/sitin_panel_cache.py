"""坐隐面板**窗口级缓存**（panel-triage 包，3.6b/c/d 共用的全量产物层）。

## 这个工具解决什么问题

任务约束（原文）：

- 「全量 35.9 万行面板的规则重算只在面板台账本身变化时执行一次，并把窗口级结果缓存为
  带指纹的产物供下游复用（禁止每个包各自重扫 29 GB）」；
- 「同一批账目由缓存复算的耗时必须 <60 秒；下游包只读缓存，不得各自重跑全量」；
- 「开发与小样本纪律：新工具先在 ≤1000 窗口的小样本验证，再放大到诊断子集
  （16,851 行），最后才允许全量（359,262 行）」。

canonical 面板是 105 份 decisions.jsonl（29 GB / 359,262 行）。每做一次逐类账、
逐类判定或面板自洽核对都重扫一遍，既贵又**必然产生口径漂移**（每个包自己算一遍）。
本工具把"一次全量规则重算"固化成窗口级产物，之后一切出账都只是折叠：

    build（一次全量）→ shards/（窗口事实）+ columns/（候选列）+ index.json
    aggregate（秒级）→ 面板账 / 面板自洽核对 / raw 诊断 —— 只读产物，不再重扫语料
    verify（秒级）  → 指纹、行数、对账恒等式逐条断言

## 两层产物与**分层失效**（Lead 2026-09-16 追加要求）

| 层 | 内容 | 绑定指纹 | 什么时候失效 |
| --- | --- | --- | --- |
| **窗口事实** shards/ | 记录层归一化、规则分析结论（合法候选、完整性）、逐类判定、面板自洽核对、raw 诊断 | facts.digest（面板指纹 + 记录层 + ruleset + base_score + you_cai_bi_kao + 记录格式版本 + 本工具哈希） | 上述任一变化 ⇒ 该层重扫 |
| **候选列** columns/ | 每个（候选身份 × 文件）一列：逐窗口 -（未测量）/ f（触发）/ c（改选）/ b（两者） | candidate.bound_identity（模块 + 有效参数 + **执行依赖闭包指纹**，取自 sitin_gates.candidate_identity） | **只失效该候选自己的列**；scorer 落地后 policy 源码变化只重算受影响的列，窗口事实不动 |

失效条件写在 index.json 的 `invalidation` 段（人读 + 机器读同一份）。候选**不假设不变**：
身份是字段，不是常量；同一文件上不同候选的列各自独立复用。

## 口径不复制（唯一重要的设计约束）

缓存**不重新实现**任何判定：它只做一次既有单一实现的**记录器**——

| 层 | 单一来源 |
| --- | --- |
| 记录层归一化 | adapters/recording/chain_piao.normalize_decision_input_payload（经 sitin_scenario_classes.normalize_record_layer） |
| 规则分析 | hangma.engine.HangmaRules.analyze |
| 逐类判定 | sitin_scenario_classes.classify_window（28 类谓词表） |
| 候选身份 | sitin_gates.candidate_identity（模块 + 有效参数 + 执行依赖指纹） |
| 候选测量 | 与 sitin_scenario_classes.evaluate_panel 逐行同序（fired / changed） |

聚合侧把两层产物**重建**成 evaluate_panel 的返回形状（records / panel / panel_facts），
再交给 coverage_ledger / class_matrix / effect_layer / gates.perclass_records
出账。于是"缓存出的账"与"直扫出的账"在**同一份实现**上取值——不存在第二套口径。

## 记录时代语义（Lead 2026-09-16 裁定 A：按时代分层核对）

a8c5df90（2026-09-09T09:23:21Z）之前，engine.py 把抓打圈的**全局旗标**直接当本座受限
（`catch_play=observation.rule_state.catch_play`，圈主不豁免）；之后改成
`analyze_catch_play(observation).restricts(seat)`（**圈主豁免**）。于是**旧记录里的合法候选
集合与当前引擎重算结果本就不具可比性**——这类窗口的面板自洽核对结果**必须按记录时代分层**，
并从逐类账的分母中剔除、单列条数（`class_scope=era_comparable`），
**不得**写成"不一致=0"，也不得混进类的 sufficient/insufficient 判定。

- `record_era_semantics`：`legacy_owner_blind`（记录时间 < 边界）/
  `current_owner_exempt`（>= 边界），按会话时间戳判定，落在**文件条目**上（逐窗口解引用）；
- `record_ruleset_version`：记录自己声明的版本（逐窗口，小字典下标）；
  **重算版本**在同段里并列（`recompute_ruleset_version`）——两者不同不代表合法性不同，
  但必须与时代标记一起读。

## 面板指纹（F13 裁定，2026-09-16）

**唯一面板指纹 = panel_fingerprint**，算法 = 对纳入文件按路径升序拼接
"path rows sha256"（换行分隔）后取 sha256。文件集合（不含行数）的指纹另存
`included_files_sha256`，**只用于文件集合对拍**，不承担面板身份。

只读：不跑桌赛、不写语料、不改候选或线上配置。
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
import gzip
import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence')
DEFAULT_PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

SCHEMA = "sitin-panel-cache/2"
#: 缓存记录格式版本：字段语义变化必须 +1（旧产物随之失效并被重扫）。
WINDOW_RECORD_VERSION = 2

#: 记录时代边界（A 裁决）：a8c5df90 提交时间 = 2026-09-09T09:23:21Z。
ERA_BOUNDARY_COMMIT = "a8c5df90"
ERA_BOUNDARY_UTC = "2026-09-09T09:23:21Z"
ERA_LEGACY = "legacy_owner_blind"
ERA_CURRENT = "current_owner_exempt"

#: 面板冻结候选身份表（与 evidence/3.6b-perclass/canonical_panel_report.py 的 WEIGHTS 一致；
#: tools/test_sitin_panel_cache.py 会**读那个文件**逐项断言，防止两处漂移）。
PANEL_CANDIDATE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "chain_path_value": {"adj.scale": 40.0},
    "four_component_path_value": {},
    "meld_opportunity_cost": {"adj.beta": 20.0},
    "meld_waiting_conditional": {"adj.gain": 60.0, "adj.reference": 21.0},
    "multiplier_path_potential": {
        "adj.scale_points_per_log2_fan": 12.0, "adj.w_chain_step_log2fan": 1.0,
        "adj.w_chain_progress_log2fan": 0.5, "adj.w_baotou_progress_log2fan": 0.5,
        "adj.w_branch_quality_log2fan": 0.5, "adj.w_four_white_ratio_log2fan": 0.5},
    "seven_pairs_path_value": {"adj.path_log2": 1.0, "adj.closer_bonus": 1.0},
}

#: 窗口状态码（**对账恒等式**用它拼：scored + 四个排除项 = 行数）。
STATUS = {
    "scored": 0,
    "excluded_decode": 1,
    "excluded_degraded": 2,
    "baseline_failed": 3,
    "candidate_failed": 4,
}
STATUS_NAMES = {value: key for key, value in STATUS.items()}

#: 面板自洽核对的三态（记录落盘合法候选 vs 本地规则重算）。
LEGAL = {"match": 0, "mismatch": 1, "recorded_absent": 2}
LEGAL_NAMES = {value: key for key, value in LEGAL.items()}

#: 候选列里的逐窗口取值：-, f, c, b（**未测量**与"没触发"必须分开）。
COLUMN_CODES = ("-", "f", "c", "b")

_ERA_RE = re.compile(r"/postgame/(\d{8}T\d{6})Z?")


# ---------------------------------------------------------------------------
# 0. 单一来源装载（复用既有实现，不复制判定）
# ---------------------------------------------------------------------------

_TOOL_CACHE: Dict[str, Any] = {}


def tool(name: str):
    """按名加载同目录/相邻证据目录的既有坐隐工具（与 sitin_scenario_classes._tool 同一手法）。"""

    if name not in _TOOL_CACHE:
        base = HERE if (_project_file(_PROJECT_ROOT, HERE / (name + ".py"))).exists() else _project_file(_PROJECT_ROOT, EVIDENCE / "3.6b-perclass")
        spec = importlib.util.spec_from_file_location(name, base / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _TOOL_CACHE[name] = module
    return _TOOL_CACHE[name]


def scenario_classes():
    return tool("sitin_scenario_classes")


def gates():
    """门禁工具：候选身份与逐类记录的**单一来源**。"""

    if "sitin_gates" not in sys.modules:
        spec = importlib.util.spec_from_file_location("sitin_gates", _project_file(_PROJECT_ROOT, HERE / "sitin_gates.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules["sitin_gates"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules["sitin_gates"]


# ---------------------------------------------------------------------------
# 1. 面板身份、指纹与时代标记
# ---------------------------------------------------------------------------

def panel_fingerprint(files: Sequence[Mapping[str, Any]]) -> str:
    """**唯一面板指纹算法**：路径升序，拼接 "path rows sha256"（换行分隔）取 sha256。

    它同时绑定**文件集合、逐文件行数与逐文件内容**，所以换文件、改行数、改内容都会变。
    与 corpus-manifest-canonical.json 的 fingerprint 同算法（F13 裁定的唯一口径）。
    """

    ordered = sorted(files, key=lambda item: str(item["path"]))
    return hashlib.sha256("\n".join(
        "{0} {1} {2}".format(item["path"], item["rows"], item["sha256"])
        for item in ordered).encode("utf-8")).hexdigest()


def included_files_sha256(files: Sequence[Mapping[str, Any]]) -> str:
    """**文件集合指纹**（不含行数）：只用于"纳入集合是否与另一处清单逐份相同"的对拍。

    它与 panel_fingerprint **不是同一件事**，不得用来标识面板身份（F13）。
    """

    ordered = sorted(files, key=lambda item: str(item["path"]))
    digest = hashlib.sha256()
    for item in ordered:
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(str(item["sha256"]).encode("utf-8"))
    return digest.hexdigest()


def record_era(path: str) -> str:
    """按会话时间戳判定"这份记录是在哪个抓打圈语义下产生的"（A 裁决的分层依据）。

    边界 = a8c5df90（2026-09-09T09:23:21Z）：之前圈内**所有座位**一律摸切，
    之后**圈主豁免**。时间戳取不到时返回 unknown（**不猜**，也不默认成任一侧）。
    """

    match = _ERA_RE.search(path)
    if not match:
        return "unknown"
    stamp = match.group(1)
    iso = "{0}-{1}-{2}T{3}:{4}:{5}Z".format(stamp[0:4], stamp[4:6], stamp[6:8],
                                            stamp[9:11], stamp[11:13], stamp[13:15])
    return ERA_LEGACY if iso < ERA_BOUNDARY_UTC else ERA_CURRENT


def resolve_era(recorded_versions: Sequence[str], recompute_ruleset: str,
                timestamp_era: str) -> Tuple[str, str]:
    """记录时代语义：**优先用记录侧自述版本**（直接证据），缺失时退回会话时间戳。

    为什么版本串优先（2026-09-16 实测）：a8c5df90 同时改了抓打圈语义**并把**默认 ruleset
    升到 `hangma-mvp-v10-public-counts`，所以"记录侧声明 v10"就是"这份记录由带圈主豁免的
    引擎产生"的直接证据；而**提交作者时间不是部署时间**——09-09 的 5 份会话（时间戳
    06:24Z—09:09Z，早于提交作者时间 09:23Z）已经声明 v10。用时间戳会把这 5 份错划进 legacy。

    返回 (era, basis)，basis 写明判定依据，供逐文件复核。
    """

    versions = sorted({str(item) for item in recorded_versions if item})
    if versions and all(item == recompute_ruleset for item in versions):
        return ERA_CURRENT, "recorded-ruleset-version==recompute:" + recompute_ruleset
    if versions:
        return ERA_LEGACY, ("recorded-ruleset-version!=recompute:" + "|".join(versions))
    return timestamp_era, "session-timestamp-fallback"


def manifest_of(path: Path) -> Optional[Dict[str, Any]]:
    """读语料清单（sitin-corpus-manifest/1）；普通 JSONL 输入返回 None。"""

    if path.suffix != ".json":
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("schema") != "sitin-corpus-manifest/1":
        return None
    return dict(data)


def panel_identity(manifest: Optional[Mapping[str, Any]], panel_path: Path,
                   rows: int) -> Dict[str, Any]:
    """面板身份四件套（panel_id + 指纹 + 行数 + record_layer_filled）+ 清单哈希。"""

    manifest = manifest or {}
    files = list(manifest.get("files") or [])
    return {
        "panel_id": manifest.get("panel_id") or panel_path.name,
        "panel_fingerprint": panel_fingerprint(files) if files else None,
        "panel_fingerprint_basis": ("F13 唯一口径：纳入文件按路径升序拼接 "
                                    "'path rows sha256' 后取 sha256"),
        "included_files_sha256": included_files_sha256(files) if files else None,
        "included_files_sha256_basis": ("文件集合指纹（不含行数）：**只**用于与另一处清单"
                                        "对拍纳入集合，不承担面板身份"),
        "manifest_sha256": (hashlib.sha256(panel_path.read_bytes()).hexdigest()
                            if manifest and panel_path.is_file() else None),
        "rows": rows if rows else manifest.get("rows"),
        "files": len(files) if files else 1,
        "record_layer_filled": bool(manifest.get("record_layer_filled")),
        "record_layer": manifest.get("record_layer"),
        "excluded_rows": manifest.get("excluded_rows"),
        "excluded_ratio": manifest.get("excluded_ratio"),
        "family_rows": manifest.get("family_rows"),
        "family_files": manifest.get("family_files"),
        "excluded_note": "排除账由清单原样透传（排除判据属清单生成器，本工具不重算）",
        "generator": manifest.get("generator"),
    }


def facts_digest(identity: Mapping[str, Any], record_layer: str, ruleset: str,
                 base_score: int, you_cai_bi_kao: bool) -> str:
    """**窗口事实层**指纹：面板 + 记录层 + 规则配置 + 记录格式版本 + 本工具哈希。

    候选身份**不在**这里（那是列层的事）：policy 源码变化不得让窗口事实失效。
    """

    payload = {
        "schema": SCHEMA,
        "window_record_version": WINDOW_RECORD_VERSION,
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "panel_fingerprint": identity.get("panel_fingerprint"),
        "record_layer": record_layer,
        "ruleset": ruleset,
        "base_score": base_score,
        "you_cai_bi_kao": you_cai_bi_kao,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def candidate_table(names: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """候选身份表：名字 → 权重 + bound_identity + 列名（身份哈希）。"""

    table: Dict[str, Dict[str, Any]] = {}
    for name in names:
        weights = dict(PANEL_CANDIDATE_WEIGHTS.get(name, {}))
        identity = gates().candidate_identity(name, weights)
        table[name] = {
            "weights": weights,
            "bound_identity": identity,
            "column_id": hashlib.sha256("{0}|{1}".format(name, identity).encode("utf-8")
                                        ).hexdigest()[:12],
        }
    return table


# ---------------------------------------------------------------------------
# 2. 扫描：一次规则重算 → 窗口事实 + 候选列
# ---------------------------------------------------------------------------

class Scanner:
    """把一个面板（或单个 JSONL 文件）扫成窗口事实与候选列的**唯一扫描实现**。

    逐行次序与 sitin_scenario_classes.evaluate_panel 完全一致：记录层归一化 →
    解码 → 规则分析 → raw 诊断 → 面板自洽核对 → 降级排除 → 基线计划 → 分类 →
    逐候选测量。差别只在**结果落盘形状**（分片 + 列，而不是内存列表）。
    """

    def __init__(self, record_layer: str = "filled",
                 ruleset: str = "hangma-mvp-v10-public-counts", base_score: int = 1,
                 you_cai_bi_kao: bool = False,
                 candidates: Sequence[str] = ()) -> None:
        from hangma_bot.application.deadline import ManualClock
        from hangma_bot.bootstrap import build_decision_codec
        from hangma_bot.hangma.catch_play import analyze_catch_play
        from hangma_bot.hangma.engine import HangmaRules
        from hangma_bot.kernel.config import RuleConfig
        from hangma_bot.offline.evaluate import translate_budget
        from hangma_bot.policy.evaluation_v1 import build_context
        from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
        from hangma_bot.policy.interface import DecisionRequest

        self.sc = scenario_classes()
        self.record_layer = record_layer
        self.ruleset = ruleset
        self.base_score = base_score
        self.you_cai_bi_kao = you_cai_bi_kao
        self.analyze_catch_play = analyze_catch_play
        self.normalize_record_layer = self.sc.normalize_record_layer
        self.classify_window = self.sc.classify_window
        self.build_context = build_context
        self.DecisionRequest = DecisionRequest
        self.translate_budget = translate_budget
        self.diagnostics = self.sc.RawCoverageDiagnostics()
        self.decode_request = build_decision_codec()["decode_request"]
        self.decode_budget = build_decision_codec()["decode_budget"]
        self.rules = HangmaRules(RuleConfig(ruleset_version=ruleset, base_score=base_score,
                                            you_cai_bi_kao=you_cai_bi_kao))
        clock = ManualClock(start_monotonic=100.0)
        self.baseline = ComparableHeuristicPolicyV2(monotonic=clock.now)
        self.recompute = tool("sitin_m4_recompute")
        #: 逐文件的小字典：记录侧 ruleset 版本与完整性（字符串列进索引，窗口里只存下标）。
        self.rulesets: List[str] = []
        self.completeness: List[str] = []
        registry = self.sc._registry()
        self.candidates: Dict[str, Any] = {}
        for name in candidates:
            self.candidates[name] = registry.build_candidate(
                name, weights=dict(PANEL_CANDIDATE_WEIGHTS.get(name, {})),
                monotonic=clock.now)

    def _code(self, table: List[str], value: Any) -> int:
        """字符串 → 逐文件小字典下标（窗口级记录保持紧凑，字典放进索引条目）。"""

        text = str(value) if value is not None else ""
        if text not in table:
            table.append(text)
        return table.index(text)

    def window(self, row: Mapping[str, Any], index: int, line: int,
               columns: Optional[Mapping[str, Callable[[str], None]]] = None
               ) -> Dict[str, Any]:
        """扫一行 → (窗口事实, 候选列码)。

        columns 非空时，逐行把每个候选的码（-) f / c / b）交给对应列的 sink；
        未走到候选测量的行写 "-"（**未测量**，与"没触发"区分开）。
        """

        sc = self.sc
        row = self.normalize_record_layer(row, self.record_layer)
        payload = row.get("request")
        record: Dict[str, Any] = {"i": index, "l": line}
        codes: Dict[str, str] = {name: "-" for name in self.candidates}

        def emit() -> Dict[str, Any]:
            if columns:
                for name, sink in columns.items():
                    sink(codes.get(name, "-"))
            return record

        if not isinstance(payload, Mapping):
            self.diagnostics.undecodable += 1
            record["s"] = STATUS["excluded_decode"]
            return emit()
        try:
            recorded = self.decode_request(payload)
            origin = row.get("budget_origin_monotonic", 0.0)
            budget = self.translate_budget(self.decode_budget(row.get("budget"), origin),
                                           origin, 100.0)
            analysis = self.rules.analyze(recorded.observation)
        except Exception:                                  # noqa: BLE001 —— 与直扫同口径
            self.diagnostics.undecodable += 1
            record["s"] = STATUS["excluded_decode"]
            return emit()
        self.diagnostics.add(recorded)
        record["k"] = str(recorded.decision_id)
        observation = recorded.observation
        state = observation.rule_state
        # 抓打圈归属事实（triage 关键字段）：当前实现判"本座是否受限"用的就是这个结果。
        attribution = self.analyze_catch_play(observation)
        record["cpa"] = [int(bool(attribution.active)),
                         -1 if attribution.owner_seat is None else attribution.owner_seat,
                         int(bool(attribution.restricts(observation.seat)))]
        if attribution.issue:
            record["cpi"] = attribution.issue
        record["cpv"] = int(bool(state.catch_play))
        record["co"] = -1 if state.catch_play_owner_seat is None else state.catch_play_owner_seat
        record["cc"] = int(state.chain_count)
        record["pw"] = observation.chain_piao
        record["bt"] = int(bool(state.baotou))
        record["wl"] = int(any(tile.code == state.wealth_god.code
                               for tile in observation.my_hand))
        record["rt"] = observation.remaining_tile_count
        record["ph"] = str(observation.phase)
        record["seat"] = int(observation.seat)
        record["dr"] = (observation.drawn_tile.code
                        if observation.drawn_tile is not None else None)
        # 记录侧自述：产生这份记录时的 ruleset 版本与完整性（面板自洽核对的分层依据之一）。
        recorded_rules_raw = payload.get("rules")
        if isinstance(recorded_rules_raw, Mapping):
            record["rs"] = self._code(self.rulesets, recorded_rules_raw.get("ruleset_version"))
            record["rc"] = self._code(self.completeness, recorded_rules_raw.get("completeness"))
            recorded_keys = {entry.get("action_key")
                             for entry in (recorded_rules_raw.get("legal_candidates") or ())}
        else:
            recorded_keys = set()
        # **面板自洽核对在降级门之前**：口径是超集——"计分窗口口径"（聚合时只数 scored）
        # 与"全部可解码行口径"都能复现，两个口径分母不同、不得相加。
        local_keys = {candidate.action_key for candidate in analysis.legal_candidates}
        if not recorded_keys:
            record["lg"] = LEGAL["recorded_absent"]
        elif recorded_keys == local_keys:
            record["lg"] = LEGAL["match"]
        else:
            # 不一致：逐键留证（只有 139 个窗口，体积可忽略）。
            record["lg"] = LEGAL["mismatch"]
            record["or"] = sorted(recorded_keys - local_keys)
            record["ol"] = sorted(local_keys - recorded_keys)
            record["rk"] = sorted(recorded_keys)
        if analysis.completeness.name == "DEGRADED" or not analysis.legal_candidates:
            record["s"] = STATUS["excluded_degraded"]
            return emit()

        request = self.DecisionRequest(
            observation=observation, competition=recorded.competition, rules=analysis,
            decision_id=recorded.decision_id, trigger_seq=recorded.trigger_seq,
            window_key=recorded.window_key, rejected_attempts=())
        try:
            base_plan = asyncio.run(self.baseline.choose(request, budget))
        except Exception:                                  # noqa: BLE001
            record["s"] = STATUS["baseline_failed"]
            return emit()
        try:
            ctx = self.build_context(observation, you_cai_bi_kao=self.you_cai_bi_kao)
            classes = self.classify_window(ctx, analysis.legal_candidates)
        except Exception:                                  # noqa: BLE001
            record["s"] = STATUS["candidate_failed"]
            return emit()
        in_class = [cid for cid in sc.CLASS_IDS if classes[cid] is True]
        undecided = [cid for cid in sc.CLASS_IDS if classes[cid] is None]
        if in_class:
            record["in"] = in_class
        if undecided:
            record["un"] = undecided
        base_first = self.recompute._first_key(base_plan)
        for name, policy in self.candidates.items():
            before = policy.adjustment.fired_count
            try:
                plan = asyncio.run(policy.choose(request, budget))
            except Exception:                              # noqa: BLE001
                record["s"] = STATUS["candidate_failed"]
                return emit()
            fired = policy.adjustment.fired_count > before
            changed = self.recompute._first_key(plan) != base_first
            codes[name] = "b" if (fired and changed) else "f" if fired else "c" if changed else "-"
        record["s"] = STATUS["scored"]
        return emit()

    def scan_file(self, path: Path, index: int, limit: Optional[int] = None,
                  sink: Optional[Callable[[Dict[str, Any]], None]] = None,
                  columns: Optional[Mapping[str, Callable[[str], None]]] = None
                  ) -> Tuple[int, bool]:
        """扫一份 decisions.jsonl；返回 (行数, 是否被 limit 截断)。"""

        rows = 0
        truncated = False
        with path.open(encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                raw = raw.strip()
                if not raw:
                    continue
                if limit is not None and rows >= limit:
                    truncated = True
                    break
                record = self.window(json.loads(raw), index, line_number, columns=columns)
                rows += 1
                if sink is not None:
                    sink(record)
        return rows, truncated


# ---------------------------------------------------------------------------
# 3. 产物读写（分片 / 列 / 哈希）
# ---------------------------------------------------------------------------

def shard_name(index: int, file_sha: str) -> str:
    return "{0:03d}-{1}.jsonl.gz".format(index, file_sha[:12])


def column_name(index: int, candidate: str, column_id: str) -> str:
    return "{0:03d}-{1}-{2}.jsonl.gz".format(index, candidate, column_id)


def read_shard(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_column(path: Path) -> List[str]:
    """读一条候选列（逐窗口一个字符，与同文件分片逐行对齐）。"""

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 4. 构建（分层失效：窗口事实一层、候选列一层）
# ---------------------------------------------------------------------------

def build(panel: Path, out: Path, *, record_layer: str = "filled",
          ruleset: str = "hangma-mvp-v10-public-counts", base_score: int = 1,
          you_cai_bi_kao: bool = False, candidates: Sequence[str] = (),
          limit: Optional[int] = None, reuse: bool = True,
          verbose: bool = True) -> Dict[str, Any]:
    """构建（或分层增量更新）缓存。

    逐文件决策：窗口事实可复用且所需候选列都在 ⇒ 整份跳过；
    否则扫一次该文件，只重写**失效的那些层**（列失效不影响窗口事实）。
    """

    manifest = manifest_of(panel)
    files = list((manifest or {}).get("files") or [])
    if not files:                                          # 普通 JSONL：单文件面板
        files = [{"path": str(panel.relative_to(ROOT)), "rows": 0,
                  "sha256": sha256_file(panel)}]
    out.mkdir(parents=True, exist_ok=True)
    (out / "shards").mkdir(exist_ok=True)
    (out / "columns").mkdir(exist_ok=True)
    table = candidate_table(candidates)
    identity = panel_identity(manifest, panel,
                              sum(int(item.get("rows") or 0) for item in files))
    digest = facts_digest(identity, record_layer, ruleset, base_score, you_cai_bi_kao)

    previous: Dict[str, Any] = {}
    index_path = out / "index.json"
    if reuse and index_path.exists():
        previous = json.loads(index_path.read_text(encoding="utf-8"))
        if previous.get("facts", {}).get("digest") != digest or not previous.get("files"):
            previous = {}

    started = time.time()
    entries: List[Dict[str, Any]] = []
    columns: Dict[str, Dict[str, Any]] = {name: {} for name in table}
    per_file_cpu: List[Dict[str, Any]] = []
    reused_files = scanned_files = 0
    reused_columns = rebuilt_columns = 0
    previous_columns: Dict[str, Dict[str, Any]] = {}
    for name, meta in table.items():
        previous_columns[name] = {
            entry["index"]: entry for entry in
            ((previous.get("candidates", {}) or {}).get(name, {}) or {}).get("columns", [])
        } if previous else {}
    for index, item in enumerate(files):
        rel = str(item["path"])
        file_sha = str(item["sha256"])
        name = shard_name(index, file_sha)
        target = out / "shards" / name
        entry_prev = None
        if previous:
            entry_prev = next((entity for entity in previous.get("files", [])
                               if entity["path"] == rel and entity["file_sha256"] == file_sha
                               and not entity.get("partial")), None)
        facts_ok = bool(entry_prev is not None and target.exists()
                        and entry_prev.get("shard_sha256") == sha256_file(target))
        # 逐候选判断列是否需要重算：身份不同、文件缺失或哈希不符 ⇒ 重算**该列**。
        pending_columns = []
        for candidate_name, meta in table.items():
            old = previous_columns[candidate_name].get(index)
            column_path = out / "columns" / column_name(index, candidate_name,
                                                        meta["column_id"])
            ok = bool(old is not None and old.get("column_id") == meta["column_id"]
                      and old.get("file_sha256") == file_sha and not old.get("partial")
                      and column_path.exists()
                      and old.get("sha256") == sha256_file(column_path))
            if ok and facts_ok:
                columns[candidate_name][str(index)] = dict(old)
                reused_columns += 1
                continue
            if ok and not facts_ok:
                # 事实层要重扫时列也要重写（列是对该次分析的测量），但仍按"列"计账。
                pending_columns.append(candidate_name)
                continue
            pending_columns.append(candidate_name)
        if facts_ok and not pending_columns:
            assert entry_prev is not None
            entries.append(dict(entry_prev))
            reused_files += 1
            per_file_cpu.append({"path": rel, "rows": entry_prev["rows"], "reused": True,
                                 "facts_rescanned": False, "columns_rebuilt": [],
                                 "sec": 0.0})
            if verbose:
                print("[build] {0:3d} {1:6d} 行 复用（事实+列）".format(
                    index, int(entry_prev["rows"])), flush=True)
            continue
        remaining = None if limit is None else max(
            0, limit - sum(int(entity["rows"]) for entity in entries))
        scanner = Scanner(record_layer=record_layer, ruleset=ruleset, base_score=base_score,
                          you_cai_bi_kao=you_cai_bi_kao, candidates=pending_columns)
        file_started = time.time()
        buffer: List[str] = []
        column_buffers = {candidate_name: [] for candidate_name in pending_columns}
        # **只在事实层需要重写时才打开分片**：事实可复用时打开 "wt" 会截断已有分片
        # （单元测试 test_candidate_column_increment_is_per_candidate 就是这样抓出来的）。
        facts_handle = None if facts_ok else gzip.open(target, "wt", encoding="utf-8")
        try:
            def sink(record: Dict[str, Any]) -> None:
                if facts_handle is None:
                    return
                buffer.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                if len(buffer) >= 2000:
                    facts_handle.write("\n".join(buffer) + "\n")
                    buffer.clear()

            def column_sink(candidate_name: str) -> Callable[[str], None]:
                def sink_code(code: str) -> None:
                    column_buffers[candidate_name].append(code)
                return sink_code

            sinks = {candidate_name: column_sink(candidate_name)
                     for candidate_name in pending_columns}
            rows, truncated = scanner.scan_file(_project_file(_PROJECT_ROOT, ROOT / rel), index, limit=remaining,
                                                sink=sink,
                                                columns=sinks if pending_columns else None)
            if facts_handle is not None and buffer:
                facts_handle.write("\n".join(buffer) + "\n")
        finally:
            if facts_handle is not None:
                facts_handle.close()
        if not facts_ok:
            entries.append({
                "index": index, "path": rel, "rows": rows, "file_sha256": file_sha,
                "shard": "shards/" + name, "partial": bool(truncated),
                "shard_sha256": sha256_file(target),
                "shard_bytes": target.stat().st_size,
                "expected_rows": int(item.get("rows") or 0),
                # era：记录时代语义（版本串优先，时间戳兜底）；era_ts 另存时间戳口径供复核。
                "era": resolve_era(scanner.rulesets, ruleset, record_era(rel))[0],
                "era_basis": resolve_era(scanner.rulesets, ruleset, record_era(rel))[1],
                "era_ts": record_era(rel),
                "rulesets": list(scanner.rulesets),
                "completeness": list(scanner.completeness),
            })
        else:
            assert entry_prev is not None
            entries.append(dict(entry_prev))
        for candidate_name in pending_columns:
            meta = table[candidate_name]
            column_path = out / "columns" / column_name(index, candidate_name,
                                                        meta["column_id"])
            with gzip.open(column_path, "wt", encoding="utf-8") as column_handle:
                for offset in range(0, len(column_buffers[candidate_name]), 4000):
                    column_handle.write("\n".join(
                        column_buffers[candidate_name][offset:offset + 4000]) + "\n")
            columns[candidate_name][str(index)] = {
                "index": index, "column_id": meta["column_id"],
                "column": "columns/" + column_name(index, candidate_name, meta["column_id"]),
                "rows": len(column_buffers[candidate_name]), "file_sha256": file_sha,
                "facts_digest": digest, "partial": bool(truncated),
                "sha256": sha256_file(column_path),
            }
            rebuilt_columns += 1
        scanned_files += 1
        per_file_cpu.append({"path": rel, "rows": rows,
                             "reused": False, "facts_rescanned": not facts_ok,
                             "columns_rebuilt": list(pending_columns),
                             "sec": round(time.time() - file_started, 2),
                             "truncated": bool(truncated)})
        if verbose:
            print("[build] {0:3d} {1:6d} 行 {2:.1f}s 扫描 事实{3} 列{4}{5}".format(
                index, rows, time.time() - file_started,
                "重算" if not facts_ok else "复用", len(pending_columns),
                " (截断)" if truncated else ""), flush=True)
        if truncated:
            break

    index_payload = {
        "schema": SCHEMA,
        "window_record_version": WINDOW_RECORD_VERSION,
        "generator": ('tools/offline/sitin/sitin_panel_cache.py'),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "panel": identity,
        "facts": {
            "record_layer": record_layer,
            "ruleset": ruleset,
            "base_score": base_score,
            "you_cai_bi_kao": you_cai_bi_kao,
            "limit": limit,
            "digest": digest,
            "digest_basis": ("面板指纹 + 记录层 + ruleset + base_score + you_cai_bi_kao + "
                             "记录格式版本 + 本工具哈希（**不含候选身份**）"),
        },
        "candidates": {
            name: {"weights": meta["weights"], "bound_identity": meta["bound_identity"],
                   "column_id": meta["column_id"],
                   "columns": [columns[name][str(entity_index)]
                               for entity_index in sorted(int(key) for key in columns[name])]}
            for name, meta in table.items()
        },
        "record_era": {
            "boundary_commit": ERA_BOUNDARY_COMMIT,
            "boundary_utc": ERA_BOUNDARY_UTC,
            "legacy": ERA_LEGACY, "current": ERA_CURRENT,
            "basis": ("a8c5df90 之前 engine.py 用全局旗标（圈内所有座位摸牌切）；之后用 "
                      "analyze_catch_play(...).restricts(seat)（圈主豁免）⇒ 旧记录的合法"
                      "候选集合与当前重算结果不具可比性，面板自洽核对必须按时代分层。"),
        },
        "files": entries,
        "build": {
            "reused_files": reused_files, "scanned_files": scanned_files,
            "reused_columns": reused_columns, "rebuilt_columns": rebuilt_columns,
            "rows_in_cache": sum(int(entity["rows"]) for entity in entries),
            "elapsed_sec": round(time.time() - started, 2),
            "per_file": per_file_cpu,
        },
        "invalidation": {
            "facts_layer": ("facts.digest 变化 ⇒ 全部窗口事实与全部候选列重扫；"
                            "分片被改动（哈希不符）⇒ 该分片重扫；--limit 截断的分片"
                            "标 partial ⇒ 全量构建一律重扫"),
            "column_layer": ("每个（候选 × 文件）列绑定该候选的 bound_identity"
                             "（模块 + 有效参数 + 执行依赖闭包指纹）与产生它的 facts.digest；"
                             "只重算失效的那一列，窗口事实层不动（scorer 落地后 policy 源码"
                             "变化即走这条路径）"),
        },
        "note": ("窗口级缓存：只读产物即可出账，不得重扫语料。候选身份是**字段**不是常量；"
                 "下游引用时必须带上 facts.digest 与逐候选 bound_identity。"),
    }
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return index_payload


# ---------------------------------------------------------------------------
# 5. 聚合与重建（只读产物，不再重扫语料）
# ---------------------------------------------------------------------------

def aggregate(cache: Path, *, emit: Optional[Path] = None,
              verbose: bool = True) -> Dict[str, Any]:
    """只读产物，折叠出面板账 + 面板自洽核对 + raw 诊断 + 记录时代分层（**不重跑规则**）。"""

    index = json.loads((cache / "index.json").read_text(encoding="utf-8"))
    started = time.time()
    counts = {name: 0 for name in STATUS}
    legal = {name: 0 for name in LEGAL}
    legal_all = {name: 0 for name in LEGAL}
    degraded_with_mismatch = 0
    diagnostics = {key: 0 for key in ("raw_windows", "undecodable", "raw_catch_play_true",
                                      "raw_catch_play_owner_known", "raw_chain_count_nonzero",
                                      "raw_chain_piao_known", "raw_chain_piao_undecidable",
                                      "raw_baotou_true", "raw_hand_holds_wealth")}
    class_windows: Dict[str, int] = {}
    class_undecided: Dict[str, int] = {}
    class_windows_comparable: Dict[str, int] = {}
    class_undecided_comparable: Dict[str, int] = {}
    per_candidate = {name: {"fired": 0, "changed": 0, "measured": 0}
                     for name in index["candidates"]}
    column_score: Dict[str, Dict[str, int]] = {name: {} for name in index["candidates"]}
    mismatches: List[Dict[str, Any]] = []
    era_counts: Dict[str, Dict[str, int]] = {
        era: {"files": 0, "rows": 0, "mismatch": 0, "scored": 0}
        for era in sorted({entry.get("era", "unknown") for entry in index["files"]})}
    era_incomparable = 0
    total_rows = 0
    column_cache: Dict[Tuple[str, int], List[str]] = {}
    era_by_file: Dict[str, Dict[str, Any]] = {}
    for entry in index["files"]:
        # era 在聚合时按**缓存内的证据**重算：记录侧版本串优先、时间戳兜底（见 resolve_era）。
        # 这样即使构建轮次早于本规则，产物仍然给出唯一口径，并且逐文件写明依据。
        era, era_basis = resolve_era(entry.get("rulesets") or (),
                                     index["facts"]["ruleset"],
                                     entry.get("era_ts") or entry.get("era") or "unknown")
        era_by_file[entry["path"]] = {"era": era, "era_basis": era_basis,
                                      "era_ts": entry.get("era_ts") or entry.get("era"),
                                      "rulesets": list(entry.get("rulesets") or [])}
        era_counts.setdefault(era, {"files": 0, "rows": 0, "mismatch": 0, "scored": 0})
        era_counts[era]["files"] += 1
        era_counts[era]["rows"] += int(entry["rows"])
        rulesets = entry.get("rulesets") or []
        completeness = entry.get("completeness") or []
        for record in read_shard(cache / entry["shard"]):
            total_rows += 1
            status = STATUS_NAMES[record["s"]]
            counts[status] += 1
            mismatch_here = record.get("lg") == LEGAL["mismatch"]
            incomparable = bool(mismatch_here and era == ERA_LEGACY)
            for cid in record.get("in", ()):
                class_windows[cid] = class_windows.get(cid, 0) + 1
                if not incomparable:
                    class_windows_comparable[cid] = class_windows_comparable.get(cid, 0) + 1
            for cid in record.get("un", ()):
                class_undecided[cid] = class_undecided.get(cid, 0) + 1
                if not incomparable:
                    class_undecided_comparable[cid] = class_undecided_comparable.get(cid, 0) + 1
            for name, meta in index["candidates"].items():
                codes = _column_for(cache, index, name, entry, column_cache)
                if codes is None or record["l"] - 1 >= len(codes):
                    continue
                code = codes[record["l"] - 1]
                column_score[name][code] = column_score[name].get(code, 0) + 1
                if code != "-":
                    per_candidate[name]["measured"] += 1
                if code in ("f", "b"):
                    per_candidate[name]["fired"] += 1
                if code in ("c", "b"):
                    per_candidate[name]["changed"] += 1
            if status == "excluded_decode":
                diagnostics["undecodable"] += 1
            else:
                diagnostics["raw_windows"] += 1
                diagnostics["raw_catch_play_true"] += record.get("cpv", 0)
                diagnostics["raw_catch_play_owner_known"] += record.get("co", -1) >= 0
                diagnostics["raw_chain_count_nonzero"] += record.get("cc", 0) > 0
                diagnostics["raw_chain_piao_known"] += record.get("pw") is not None
                diagnostics["raw_chain_piao_undecidable"] += (
                    record.get("pw") is None and record.get("cc", 0) > 0)
                diagnostics["raw_baotou_true"] += record.get("bt", 0)
                diagnostics["raw_hand_holds_wealth"] += record.get("wl", 0)
            if record.get("lg") is not None:
                legal_all[LEGAL_NAMES[record["lg"]]] += 1
                if status != "scored" and mismatch_here:
                    degraded_with_mismatch += 1
            if record.get("lg") is not None and status == "scored":
                legal[LEGAL_NAMES[record["lg"]]] += 1
                era_counts[era]["scored"] += 1
            if mismatch_here:
                era_counts[era]["mismatch"] += 1
                era_incomparable += int(incomparable)
                mismatches.append({
                    "window": record.get("k"), "path": entry["path"], "line": record["l"],
                    "seat": record.get("seat"), "status": status, "era": era,
                    "comparable_to_current_engine": not incomparable,
                    "only_recorded": record.get("or", []),
                    "only_local": record.get("ol", []),
                    "recorded_keys": record.get("rk", []),
                    "record_ruleset": (rulesets[record["rs"]]
                                       if record.get("rs") is not None
                                       and record["rs"] < len(rulesets) else None),
                    "record_completeness": (completeness[record["rc"]]
                                            if record.get("rc") is not None
                                            and record["rc"] < len(completeness) else None),
                    "catch_play": record.get("cpv"), "owner_seat": record.get("co"),
                    "circle": record.get("cpa"), "chain_count": record.get("cc"),
                    "holds_wealth_god": bool(record.get("wl")),
                    "drawn_tile": record.get("dr"), "phase": record.get("ph"),
                    "remaining_tile_count": record.get("rt"),
                })
    panel = {
        "rows_total": total_rows,
        "rows_seen": total_rows,
        "record_layer": index["facts"]["record_layer"],
        "scored": counts["scored"],
        "excluded_decode": counts["excluded_decode"],
        "excluded_degraded": counts["excluded_degraded"],
        "baseline_failed": counts["baseline_failed"],
        "candidate_failed": counts["candidate_failed"],
        "accounting_sum": sum(counts.values()),
        "reconciles": sum(counts.values()) == total_rows,
        "legal_reconciliation": dict(legal, note=(
            "本地规则重算的合法候选与记录落盘合法候选相同的窗口数（**计分窗口口径**，"
            "与覆盖账 legal_reconciliation 同口径）。**按记录时代分层**："
            "legacy 时代的记录由旧抓打圈语义产生，其不一致属读取注意项，"
            "已从逐类账分母剔除，见 record_era_layering。")),
        "raw_coverage": dict(diagnostics, note=(
            "raw 层覆盖诊断（字段与 sitin_scenario_classes.RawCoverageDiagnostics 一致），"
            "只描述输入面板，不参与任何 verdict。")),
    }
    payload = {
        "schema": "sitin-panel-cache-aggregate/2",
        "panel": index["panel"],
        "facts_digest": index["facts"]["digest"],
        "candidates": {name: {"bound_identity": meta["bound_identity"],
                              "column_id": meta["column_id"]}
                       for name, meta in index["candidates"].items()},
        "panel_account": panel,
        "candidate_windows": per_candidate,
        "candidate_column_codes": column_score,
        "class_windows": class_windows,
        "class_undecided": class_undecided,
        "class_windows_era_comparable": class_windows_comparable,
        "class_undecided_era_comparable": class_undecided_comparable,
        "record_era_layering": {
            "by_era": era_counts,
            "resolve_rule": ("era = recorded-ruleset-version!=recompute ⇒ legacy_owner_blind；"
                             "否则 current_owner_exempt；无版本串时退回会话时间戳"),
            "by_file": era_by_file,
            "era_incomparable_windows": era_incomparable,
            "class_scope": ("逐类账的默认分母口径 = era_comparable（剔除 legacy 时代"
                            "legal mismatch 的窗口）；这些窗口在 all 口径里仍逐条列出，"
                            "**不得**写成不一致=0，也不得混入类的 sufficient/insufficient。"),
        },
        "legal_two_denominators": {
            "scored_only": dict(legal),
            "all_decodable_rows": dict(legal_all),
            "degraded_rows_with_mismatch": degraded_with_mismatch,
            "note": ("两个口径**分母不同、不得相加**：scored_only 与覆盖账 "
                     "panel.legal_reconciliation 同口径；all_decodable_rows 与逐行探针"
                     "（probe_legal_mismatch.py 的 139）同口径。"),
        },
        "mismatches": mismatches,
        "elapsed_sec": round(time.time() - started, 2),
        "note": ("本聚合只读窗口级产物；任何下游都不得为同一批账目重扫语料。"
                 "候选列按 bound_identity 绑定，未登记的候选**不出现在** candidate_windows。"),
    }
    (cache / "aggregate.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if verbose:
        print(json.dumps({"rows": total_rows, "scored": counts["scored"],
                          "match": legal["match"], "mismatch": legal["mismatch"],
                          "absent": legal["recorded_absent"],
                          "era_incomparable": era_incomparable,
                          "elapsed_sec": payload["elapsed_sec"]}, ensure_ascii=False))
    if emit is not None:
        emit_ledgers(cache, index, emit)
    return payload


def _column_for(cache: Path, index: Mapping[str, Any], candidate: str,
                entry: Mapping[str, Any], column_cache: Dict[Tuple[str, int], List[str]]
                ) -> Optional[List[str]]:
    """取（候选 × 文件）的列（惰性读入并缓存；缺失即返回 None —— 不补 False）。"""

    key = (candidate, int(entry["index"]))
    if key in column_cache:
        return column_cache[key]
    meta = index["candidates"].get(candidate) or {}
    match = next((item for item in meta.get("columns", [])
                  if int(item["index"]) == int(entry["index"])), None)
    if match is None:
        column_cache[key] = None            # type: ignore[assignment]
        return None
    codes = read_column(cache / match["column"])
    if len(codes) != int(entry["rows"]):
        column_cache[key] = None            # type: ignore[assignment]
        return None
    column_cache[key] = codes
    return codes


def evaluation_from_cache(cache: Path, index: Optional[Mapping[str, Any]] = None,
                          class_scope: str = "era_comparable") -> Dict[str, Any]:
    """把**两层产物**重建成 evaluate_panel 的返回形状（供既有单一实现出账）。

    class_scope：

    - era_comparable（默认）：剔除 legacy 时代 legal mismatch 的窗口 —— 它们由旧抓打圈
      语义产生，与当前引擎不具可比性（A 裁决：从逐类账分母剔除并单列条数）；
    - `all`：不剔除（仅供对照；引用时必须与 era_incomparable_windows 一起给）。

    per_candidate 只包含**已登记**的候选身份；缺哪个候选就不写哪个候选
    （绝不静默补 False —— 那会把"没测"写成"没触发"）。
    """

    index = dict(index or json.loads((cache / "index.json").read_text(encoding="utf-8")))
    names = list(index["candidates"])
    records: List[Dict[str, Any]] = []
    excluded = 0
    for entry in index["files"]:
        era = resolve_era(entry.get("rulesets") or (), index["facts"]["ruleset"],
                          entry.get("era_ts") or entry.get("era") or "unknown")[0]
        column_cache: Dict[Tuple[str, int], List[str]] = {}
        codes_by_candidate = {name: _column_for(cache, index, name, entry, column_cache)
                              for name in names}
        for record in read_shard(cache / entry["shard"]):
            if record["s"] != STATUS["scored"]:
                continue
            if class_scope == "era_comparable" and era == ERA_LEGACY and \
                    record.get("lg") == LEGAL["mismatch"]:
                excluded += 1
                continue
            per_candidate = {}
            for name in names:
                codes = codes_by_candidate.get(name)
                if codes is None or record["l"] - 1 >= len(codes):
                    continue
                code = codes[record["l"] - 1]
                per_candidate[name] = {"fired": code in ("f", "b"),
                                       "changed": code in ("c", "b")}
            records.append({
                "window": record.get("k"),
                "in_class": list(record.get("in", ())),
                "undecided": list(record.get("un", ())),
                "per_candidate": per_candidate,
                "cache_index": record["i"], "cache_line": record["l"],
                "record_era": era,
                "cache_legal": (LEGAL_NAMES[record["lg"]]
                                if record.get("lg") is not None else None),
            })
    payload = json.loads((cache / "aggregate.json").read_text(encoding="utf-8"))
    panel = dict(payload["panel_account"])
    panel["class_scope"] = class_scope
    panel["class_scope_excluded_windows"] = excluded
    if class_scope == "era_comparable":
        panel["legal_reconciliation"] = dict(panel["legal_reconciliation"], note=(
            panel["legal_reconciliation"]["note"] +
            " 本 evaluation 的逐类账已按 era_comparable 剔除 {} 个时代不可比窗口。".format(
                excluded)))
    return {
        "records": records,
        "panel": panel,
        "panel_facts": {
            "ruleset_version": index["facts"]["ruleset"],
            "base_score": index["facts"]["base_score"],
            "record_layer": index["facts"]["record_layer"],
            "you_cai_bi_kao": index["facts"]["you_cai_bi_kao"],
            "class_scope": class_scope,
            "era_incomparable_windows": payload["record_era_layering"][
                "era_incomparable_windows"],
            "note": "本 evaluation 由窗口级缓存重建（同一批账目不得再扫语料）。",
        },
    }


def emit_ledgers(cache: Path, index: Mapping[str, Any], emit: Path,
                 class_scope: str = "era_comparable") -> Dict[str, Any]:
    """用**既有单一实现**从缓存出账：覆盖账 + 矩阵 + 效果层 + 逐候选 G-2C。"""

    sc = scenario_classes()
    evaluation = evaluation_from_cache(cache, index, class_scope=class_scope)
    candidates = list(index["candidates"])
    if not candidates:
        return {"emitted": False, "reason": "缓存未登记候选身份，无法出逐候选账"}
    manifest = dict(index["panel"])
    input_info = {
        "path": str(cache), "sha256": manifest.get("panel_fingerprint"),
        "rows": manifest.get("rows"), "constructed": False, "evidence_kind": "admission",
        "record_layer": index["facts"]["record_layer"], "manifest": manifest,
        "panel_identity": manifest,
    }
    emit.mkdir(parents=True, exist_ok=True)
    coverage = sc.coverage_ledger(input_info, evaluation, candidates)
    coverage["boundaries"] = list(sc.BOUNDARIES)
    coverage["class_scope"] = {
        "scope": class_scope,
        "excluded_windows": evaluation["panel"]["class_scope_excluded_windows"],
        "era_incomparable_windows": evaluation["panel_facts"]["era_incomparable_windows"],
        "note": ("era_comparable = 按记录时代分层：legacy 时代（a8c5df90 之前的抓打圈语义）"
                 "的 legal mismatch 窗口不进分母，单列条数。"),
    }
    (emit / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (emit / "COVERAGE.md").write_text(sc.render_coverage_markdown(coverage), encoding="utf-8")
    matrix = sc.class_matrix(coverage)
    (emit / "matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (emit / "MATRIX.md").write_text(sc.render_matrix_markdown(matrix), encoding="utf-8")
    effect = sc.effect_layer(input_info, evaluation, candidates)
    (emit / "effect-layer.json").write_text(
        json.dumps(effect, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (emit / "EFFECT-LAYER.md").write_text(sc.render_effect_layer_markdown(effect),
                                          encoding="utf-8")
    for name in candidates:
        record = gates().perclass_records(
            evaluation, name, weights=dict(index["candidates"][name]["weights"]),
            ruleset=index["facts"]["ruleset"], raw_diagnostics=True)
        (emit / "g2c-{0}.json".format(name)).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"emitted": True, "candidates": candidates,
            "verdict_counts": coverage["summary"]["verdict_counts"],
            "class_scope": class_scope,
            "excluded_windows": evaluation["panel"]["class_scope_excluded_windows"]}


# ---------------------------------------------------------------------------
# 6. 校验
# ---------------------------------------------------------------------------

def verify(cache: Path, verbose: bool = True) -> Dict[str, Any]:
    """逐条断言缓存的自洽性；任一不成立即非零退出（fail-closed）。"""

    index = json.loads((cache / "index.json").read_text(encoding="utf-8"))
    problems: List[str] = []
    if index.get("schema") != SCHEMA:
        problems.append("schema 不是 {0}".format(SCHEMA))
    for entry in index["files"]:
        shard = cache / entry["shard"]
        if not shard.exists():
            problems.append("分片缺失：{0}".format(entry["shard"]))
            continue
        if sha256_file(shard) != entry["shard_sha256"]:
            problems.append("分片哈希不符：{0}".format(entry["shard"]))
    for name, meta in index["candidates"].items():
        for column in meta["columns"]:
            path = cache / column["column"]
            if not path.exists():
                problems.append("候选列缺失：{0}".format(column["column"]))
                continue
            if sha256_file(path) != column["sha256"]:
                problems.append("候选列哈希不符：{0}".format(column["column"]))
            owner = next((entry for entry in index["files"]
                          if int(entry["index"]) == int(column["index"])), None)
            if owner is not None and int(owner["rows"]) != int(column["rows"]):
                problems.append("候选列行数与分片不符：{0}".format(column["column"]))
    rows_in_cache = sum(int(entry["rows"]) for entry in index["files"])
    if rows_in_cache != index["build"]["rows_in_cache"]:
        problems.append("索引行数不符：{0} != {1}".format(
            rows_in_cache, index["build"]["rows_in_cache"]))
    payload = aggregate(cache, verbose=False)
    panel = payload["panel_account"]
    if not panel["reconciles"]:
        problems.append("面板对账不成立：{0} != {1}".format(
            panel["accounting_sum"], panel["rows_total"]))
    if panel["rows_total"] != rows_in_cache:
        problems.append("聚合行数不符：{0} != {1}".format(panel["rows_total"], rows_in_cache))
    legal = panel["legal_reconciliation"]
    if legal["match"] + legal["mismatch"] + legal["recorded_absent"] != panel["scored"]:
        problems.append("面板自洽核对不守恒：{0}+{1}+{2} != {3}".format(
            legal["match"], legal["mismatch"], legal["recorded_absent"], panel["scored"]))
    if index["panel"].get("rows") and not index["facts"].get("limit") and \
            rows_in_cache != index["panel"]["rows"]:
        problems.append("缓存行数与面板声明不符：{0} != {1}".format(
            rows_in_cache, index["panel"]["rows"]))
    result = {"ok": not problems, "problems": problems, "rows": rows_in_cache,
              "panel_fingerprint": index["panel"].get("panel_fingerprint"),
              "facts_digest": index["facts"]["digest"],
              "scored": panel["scored"], "mismatch": legal["mismatch"],
              "match": legal["match"], "recorded_absent": legal["recorded_absent"],
              "era_incomparable_windows": payload["record_era_layering"][
                  "era_incomparable_windows"],
              "reused_files": index["build"]["reused_files"],
              "reused_columns": index["build"]["reused_columns"]}
    if verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="坐隐面板窗口级缓存（build / aggregate / verify）")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL), help="语料清单或 JSONL")
    parser.add_argument("--out", default=None, help="缓存目录（build）")
    parser.add_argument("--cache", default=None, help="缓存目录（aggregate / verify）")
    parser.add_argument("--record-layer", default="filled", choices=("filled", "raw"))
    parser.add_argument("--ruleset", default="hangma-mvp-v10-public-counts")
    parser.add_argument("--base-score", type=int, default=1)
    parser.add_argument("--you-cai-bi-kao", default="false", choices=("false", "true"))
    parser.add_argument("--candidates", default=",".join(sorted(PANEL_CANDIDATE_WEIGHTS)),
                        help="登记进缓存的候选身份（逗号分隔；空串=只缓存窗口事实）")
    parser.add_argument("--limit", type=int, default=None, help="行数上限（小样本/诊断子集）")
    parser.add_argument("--no-reuse", action="store_true", help="忽略既有产物，全部重扫")
    parser.add_argument("--aggregate", action="store_true", help="只做聚合（不重扫语料）")
    parser.add_argument("--verify", action="store_true", help="校验缓存自洽性")
    parser.add_argument("--emit", default=None, help="用缓存出账（目录；需已登记候选）")
    parser.add_argument("--class-scope", default="era_comparable",
                        choices=("era_comparable", "all"),
                        help="逐类账分母口径（默认按记录时代分层剔除不可比窗口）")
    args = parser.parse_args(argv)

    if args.verify:
        return 0 if verify(Path(args.cache or args.out)).get("ok") else 2
    if args.aggregate:
        cache = Path(args.cache or args.out)
        payload = aggregate(cache)
        if args.emit:
            emit_ledgers(cache,
                         json.loads((cache / "index.json").read_text(encoding="utf-8")),
                         Path(args.emit), class_scope=args.class_scope)
        del payload
        return 0
    if args.out is None:
        parser.error("build 需要 --out")
    names = tuple(name.strip() for name in args.candidates.split(",") if name.strip())
    index = build(Path(args.panel), Path(args.out), record_layer=args.record_layer,
                  ruleset=args.ruleset, base_score=args.base_score,
                  you_cai_bi_kao=args.you_cai_bi_kao == "true", candidates=names,
                  limit=args.limit, reuse=not args.no_reuse)
    print(json.dumps({"rows_in_cache": index["build"]["rows_in_cache"],
                      "reused_files": index["build"]["reused_files"],
                      "scanned_files": index["build"]["scanned_files"],
                      "rebuilt_columns": index["build"]["rebuilt_columns"],
                      "elapsed_sec": index["build"]["elapsed_sec"],
                      "panel_fingerprint": index["panel"]["panel_fingerprint"],
                      "facts_digest": index["facts"]["digest"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
