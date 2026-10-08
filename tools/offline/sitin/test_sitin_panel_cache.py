"""面板窗口级缓存自测（panel-triage 包，3.6b/c/d 共用的全量产物层）。

三条纪律（与本包 README 的边界一致）：

1. **缓存不得引入第二套口径**：同一批窗口上"缓存出账"必须与"直扫出账"逐项相等
   （面板账 / 面板自洽核对 / raw 诊断 / 逐类窗口数 / 逐候选 fired·changed）。
2. **失效必须 fail-closed**：参数指纹变化 ⇒ 分片不复用（"换配置不换缓存"是静默错）；
   --limit 截断的分片标 partial 且全量构建一律重扫；分片被改动 ⇒ verify 必须红。
3. **指纹只能有一个口径**（F13）：panel_fingerprint 与文件集合指纹 included_files_sha256
   是两个不同的量，测试同时钉住"换行数只动前者"这个语义。

缓存只读语料：不跑桌赛、不调用搜索或确认预算、不改候选与线上配置。
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

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
_EVIDENCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence')
PANEL_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json')
CANONICAL_REPORT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/canonical_panel_report.py')
CORPUS_AUDIT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6d-corpus/corpus-audit.json')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("sitin_panel_cache",
                                               _project_file(_PROJECT_ROOT, _HERE / "sitin_panel_cache.py"))
pc = importlib.util.module_from_spec(_spec)
sys.modules["sitin_panel_cache"] = pc
assert _spec.loader is not None
_spec.loader.exec_module(pc)

sc = pc.scenario_classes()
#: 小样本窗口数：等价性测试用（**不**跑全量；全量由 repro.sh 里的单次构建负责）。
SLICE = 150


def _manifest() -> dict:
    return json.loads(PANEL_MANIFEST.read_text(encoding="utf-8"))


def _mini_manifest(tmp_path: Path, rows: int) -> Path:
    """用真实面板的第一份文件造一份**单文件清单**（小样本，不物化整份语料行）。"""

    manifest = _manifest()
    first = dict(manifest["files"][0])
    mini = dict(manifest)
    mini["files"] = [first]
    mini["rows"] = rows
    mini["panel_id"] = "panel-canonical-20260910-slice"
    target = tmp_path / "mini-manifest.json"
    target.write_text(json.dumps(mini, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# 1. 指纹（F13：唯一算法 + 字段名）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_panel_fingerprint_matches_frozen_manifest() -> None:
    """唯一面板指纹必须与冻结清单现算同值（算法与口径都不许漂移）。"""

    manifest = _manifest()
    computed = pc.panel_fingerprint(manifest["files"])
    assert computed == manifest["fingerprint"]
    assert computed == "c1d3155b6e981b921cd9a1d50a3f4d90ba5b80e5df20fdf2f731f4485224c5db"


@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_included_files_sha256_is_the_file_set_fingerprint_not_the_panel_identity() -> None:
    """文件集合指纹是**另一个量**：与 corpus 包的 included_sha256 同值，但不等于面板身份。"""

    manifest = _manifest()
    file_set = pc.included_files_sha256(manifest["files"])
    assert file_set != pc.panel_fingerprint(manifest["files"])
    if CORPUS_AUDIT.exists():
        audit = json.loads(CORPUS_AUDIT.read_text(encoding="utf-8"))
        assert file_set == audit["baseline"]["selection"]["included_sha256"]


def test_fingerprint_reacts_to_rows_but_file_set_fingerprint_does_not() -> None:
    """换行数只动 panel_fingerprint（F13 的语义边界必须可失败）。"""

    files = [{"path": "a/decisions.jsonl", "rows": 10, "sha256": "aa"},
             {"path": "b/decisions.jsonl", "rows": 20, "sha256": "bb"}]
    same_but_rows = [dict(files[0], rows=11), dict(files[1])]
    assert pc.panel_fingerprint(files) != pc.panel_fingerprint(same_but_rows)
    assert pc.included_files_sha256(files) == pc.included_files_sha256(same_but_rows)


def test_fingerprint_order_is_path_sorted() -> None:
    """清单文件顺序变化不得改变指纹（路径升序是算法的一部分）。"""

    files = [{"path": "b", "rows": 1, "sha256": "2"}, {"path": "a", "rows": 1, "sha256": "1"}]
    assert pc.panel_fingerprint(files) == pc.panel_fingerprint(list(reversed(files)))


@pytest.mark.skipif(not CANONICAL_REPORT.exists(), reason="canonical 报告脚本不可用")
def test_candidate_weights_do_not_drift_from_canonical_report() -> None:
    """缓存登记的候选权重必须与 canonical 报告脚本**逐项相同**（两处漂移即身份漂移）。"""

    spec = importlib.util.spec_from_file_location("canonical_panel_report", CANONICAL_REPORT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert dict(module.WEIGHTS) == dict(pc.PANEL_CANDIDATE_WEIGHTS)
    assert tuple(module.CANDIDATES) == tuple(sorted(pc.PANEL_CANDIDATE_WEIGHTS))


# ---------------------------------------------------------------------------
# 2. 等价性：缓存 == 直扫（同一批窗口、同一份实现）
# ---------------------------------------------------------------------------

def _class_counts(evaluation: dict) -> tuple:
    windows: dict = {}
    undecided: dict = {}
    for record in evaluation["records"]:
        for cid in record.get("in_class", ()):
            windows[cid] = windows.get(cid, 0) + 1
        for cid in record.get("undecided", ()):
            undecided[cid] = undecided.get(cid, 0) + 1
    return windows, undecided


@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_cache_equals_direct_scan_on_small_slice(tmp_path: Path) -> None:
    """小样本逐项等价：面板账、自洽核对、raw 诊断、逐类窗口、逐候选 fired/changed。"""

    mini = _mini_manifest(tmp_path, SLICE)
    candidates = tuple(sorted(pc.PANEL_CANDIDATE_WEIGHTS))
    out = tmp_path / "cache"
    pc.build(mini, out, candidates=candidates, limit=SLICE, verbose=False)
    pc.aggregate(out, verbose=False)
    cached = pc.evaluation_from_cache(out)
    direct = sc.evaluate_panel(
        sc.iter_rows(mini, limit=SLICE), candidates,
        ruleset="hangma-mvp-v10-public-counts",
        weights_by_candidate={name: dict(pc.PANEL_CANDIDATE_WEIGHTS[name])
                              for name in candidates},
        record_layer="filled", diagnostics=True)
    for key in ("rows_total", "scored", "excluded_decode", "excluded_degraded",
                "baseline_failed", "candidate_failed", "accounting_sum", "reconciles"):
        assert cached["panel"][key] == direct["panel"][key], key
    for key in ("match", "mismatch", "recorded_absent"):
        assert (cached["panel"]["legal_reconciliation"][key]
                == direct["panel"]["legal_reconciliation"][key]), key
    for key, value in direct["panel"]["raw_coverage"].items():
        if key != "note":
            assert cached["panel"]["raw_coverage"][key] == value, key
    assert _class_counts(cached) == _class_counts(direct)


@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_rebuild_reuses_shards_and_does_not_rescan(tmp_path: Path) -> None:
    """未变更文件必须复用：第二次构建 scanned_shards=0、reused_shards=1。

    注意用**完整**（不带 --limit）的单文件清单：截断分片按设计不复用，
    复用语义只对"整份文件"成立（见 test_partial_shard_is_never_reused_by_a_full_build）。
    """

    mini = _mini_manifest(tmp_path, SLICE)
    out = tmp_path / "cache"
    first = pc.build(mini, out, candidates=(), verbose=False)
    second = pc.build(mini, out, candidates=(), verbose=False)
    assert first["files"][0]["partial"] is False
    assert first["build"]["scanned_files"] == 1
    assert second["build"]["scanned_files"] == 0
    assert second["build"]["reused_files"] == 1
    assert second["build"]["rows_in_cache"] == first["build"]["rows_in_cache"]
    assert second["facts"]["digest"] == first["facts"]["digest"]


@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_parameter_change_invalidates_every_shard(tmp_path: Path) -> None:
    """参数指纹变化 ⇒ 旧分片一律不复用（换配置不换缓存必须做不到）。"""

    mini = _mini_manifest(tmp_path, SLICE)
    out = tmp_path / "cache"
    pc.build(mini, out, candidates=(), limit=SLICE, verbose=False)
    other = pc.build(mini, out, candidates=(), limit=SLICE, you_cai_bi_kao=True,
                     verbose=False)
    assert other["build"]["reused_files"] == 0
    assert other["build"]["scanned_files"] == 1
    assert other["facts"]["you_cai_bi_kao"] is True


@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_partial_shard_is_never_reused_by_a_full_build(tmp_path: Path) -> None:
    """--limit 截断的分片标 partial；全量构建必须重扫它（不拿半份当全量）。"""

    mini = _mini_manifest(tmp_path, SLICE)
    out = tmp_path / "cache"
    partial = pc.build(mini, out, candidates=(), limit=SLICE, verbose=False)
    assert partial["files"][0]["partial"] is True
    full = pc.build(mini, out, candidates=(), verbose=False)
    assert full["files"][0]["partial"] is False
    assert full["build"]["reused_files"] == 0


# ---------------------------------------------------------------------------
# 3. 聚合 / 校验（用**手工造的**分片钉住口径，不依赖语料）
# ---------------------------------------------------------------------------

def _write_cache(tmp_path: Path, records: list, *,
                 rulesets=("hangma-mvp-v10-public-counts",),
                 completeness=("complete",), era_ts: Optional[str] = None,
                 column: Optional[list] = None, candidate: str = "chain_path_value"
                 ) -> Path:
    """手工造一份两层产物（事实分片 + 可选候选列），用于钉住聚合并口径。"""

    cache = tmp_path / "cache"
    (cache / "shards").mkdir(parents=True, exist_ok=True)
    (cache / "columns").mkdir(parents=True, exist_ok=True)
    shard = cache / "shards" / "000-deadbeef.jsonl.gz"
    with gzip.open(shard, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    candidates: dict = {}
    if column is not None:
        column_path = cache / "columns" / "000-chain_path_value-abc123.jsonl.gz"
        with gzip.open(column_path, "wt", encoding="utf-8") as handle:
            handle.write("\n".join(column) + "\n")
        candidates[candidate] = {
            "weights": {}, "bound_identity": "test|identity", "column_id": "abc123",
            "columns": [{"index": 0, "column_id": "abc123",
                         "column": "columns/000-chain_path_value-abc123.jsonl.gz",
                         "rows": len(column), "file_sha256": "deadbeef",
                         "facts_digest": "d" * 64, "partial": False,
                         "sha256": pc.sha256_file(column_path)}]}
    index = {
        "schema": pc.SCHEMA,
        "window_record_version": pc.WINDOW_RECORD_VERSION,
        "generator": "test",
        "panel": {"panel_id": "synthetic", "panel_fingerprint": "f" * 64, "rows": len(records),
                  "record_layer_filled": True},
        "facts": {"record_layer": "filled", "ruleset": "hangma-mvp-v10-public-counts",
                  "base_score": 1, "you_cai_bi_kao": False, "limit": None, "digest": "d" * 64},
        "candidates": candidates,
        "files": [{"index": 0, "path": "a/decisions.jsonl", "rows": len(records),
                   "file_sha256": "deadbeef", "shard": "shards/000-deadbeef.jsonl.gz",
                   "partial": False, "shard_sha256": pc.sha256_file(shard),
                   "era_ts": era_ts, "rulesets": list(rulesets),
                   "completeness": list(completeness)}],
        "build": {"reused_files": 0, "scanned_files": 1, "reused_columns": 0,
                  "rebuilt_columns": 0, "rows_in_cache": len(records),
                  "elapsed_sec": 0.0, "per_file": []},
    }
    (cache / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    return cache


def test_aggregate_keeps_two_denominators_apart(tmp_path: Path) -> None:
    """计分口径与逐行口径**不得相加**：降级行上的不一致单列在 all 口径里。"""

    records = [
        {"i": 0, "l": 1, "k": "w1", "s": pc.STATUS["scored"], "lg": pc.LEGAL["match"]},
        {"i": 0, "l": 2, "k": "w2", "s": pc.STATUS["scored"], "lg": pc.LEGAL["mismatch"],
         "or": [], "ol": ["discard:1w"], "rk": ["discard:2w"], "cpv": 1, "co": -1,
         "cpa": [1, 2, 1], "cc": 0, "wl": 1, "ph": "draw", "dr": "2w", "seat": 1},
        {"i": 0, "l": 3, "k": "w3", "s": pc.STATUS["excluded_degraded"],
         "lg": pc.LEGAL["mismatch"], "or": [], "ol": ["discard:3w"], "rk": ["discard:4w"]},
    ]
    cache = _write_cache(tmp_path, records)
    payload = pc.aggregate(cache, verbose=False)
    assert payload["legal_two_denominators"]["scored_only"]["mismatch"] == 1
    assert payload["legal_two_denominators"]["all_decodable_rows"]["mismatch"] == 2
    assert payload["panel_account"]["legal_reconciliation"]["mismatch"] == 1
    statuses = sorted(item["status"] for item in payload["mismatches"])
    assert statuses == ["excluded_degraded", "scored"]
    assert payload["panel_account"]["reconciles"] is True


def test_verify_is_fail_closed_on_tampered_shard(tmp_path: Path) -> None:
    """分片被改动 ⇒ verify 报红并给出具体分片（不让坏缓存静默出账）。"""

    records = [{"i": 0, "l": 1, "k": "w1", "s": pc.STATUS["scored"],
                "lg": pc.LEGAL["match"]}]
    cache = _write_cache(tmp_path, records)
    assert pc.verify(cache, verbose=False)["ok"] is True
    with gzip.open(cache / "shards/000-deadbeef.jsonl.gz", "at", encoding="utf-8") as handle:
        handle.write(json.dumps({"i": 0, "l": 2, "k": "w2", "s": pc.STATUS["scored"]}) + "\n")
    result = pc.verify(cache, verbose=False)
    assert result["ok"] is False
    assert any("分片哈希不符" in problem for problem in result["problems"])


def test_verify_detects_accounting_breakage(tmp_path: Path) -> None:
    """面板对账不成立（状态码未知或行数不符）必须报红。"""

    records = [{"i": 0, "l": 1, "k": "w1", "s": pc.STATUS["scored"],
                "lg": pc.LEGAL["match"]}]
    cache = _write_cache(tmp_path, records)
    index = json.loads((cache / "index.json").read_text(encoding="utf-8"))
    index["build"]["rows_in_cache"] = 5
    (cache / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    result = pc.verify(cache, verbose=False)
    assert result["ok"] is False
    assert any("索引行数不符" in problem for problem in result["problems"])


def test_evaluation_from_cache_never_invents_candidate_flags(tmp_path: Path) -> None:
    """未登记候选时**不写**该候选（绝不把"没测"写成"没触发"）。"""

    records = [{"i": 0, "l": 1, "k": "w1", "s": pc.STATUS["scored"], "lg": pc.LEGAL["match"],
                "in": ["chain.open"], "pc": {"chain_path_value": "b"}}]
    cache = _write_cache(tmp_path, records)
    pc.aggregate(cache, verbose=False)
    evaluation = pc.evaluation_from_cache(cache)
    assert evaluation["records"][0]["per_candidate"] == {}
    assert evaluation["records"][0]["in_class"] == ["chain.open"]


def test_mismatch_detail_resolves_ruleset_and_completeness(tmp_path: Path) -> None:
    """记录侧 ruleset / 完整性按逐文件字典解引用（面板自洽核对的两个来源可分开看）。"""

    records = [{"i": 0, "l": 9, "k": "w9", "s": pc.STATUS["scored"], "lg": pc.LEGAL["mismatch"],
                "or": [], "ol": ["discard:1w"], "rk": ["discard:2w"], "rs": 0, "rc": 0,
                "cpv": 1, "cpa": [1, 3, 0], "seat": 3, "dr": "2w"}]
    cache = _write_cache(tmp_path, records, rulesets=("hangma-mvp-v4-youcai-baotou",),
                         completeness=("complete",))
    payload = pc.aggregate(cache, verbose=False)
    detail = payload["mismatches"][0]
    assert detail["record_ruleset"] == "hangma-mvp-v4-youcai-baotou"
    assert detail["record_completeness"] == "complete"
    assert detail["seat"] == 3


def test_panel_identity_reports_excluded_account_by_passthrough() -> None:
    """排除账由清单**原样透传**（本工具不重算排除判据）。"""

    manifest = {"panel_id": "p", "rows": 3, "excluded_rows": 7, "excluded_ratio": 0.7,
                "family_rows": 10, "family_files": 2, "record_layer": "filled",
                "record_layer_filled": True,
                "files": [{"path": "a", "rows": 3, "sha256": "aa"}]}
    identity = pc.panel_identity(manifest, Path("panel.json"), 3)
    assert identity["excluded_rows"] == 7
    assert identity["panel_fingerprint"] == pc.panel_fingerprint(manifest["files"])
    assert identity["manifest_sha256"] is None

@pytest.mark.skipif(not PANEL_MANIFEST.exists(), reason="canonical 清单不可用")
def test_candidate_column_increment_is_per_candidate(tmp_path: Path) -> None:
    """新增/变更**一个候选**只重算该候选的列：窗口事实层不动、别的列不重写（D 裁决）。

    这条测试能失败：若实现把候选身份混进窗口事实指纹，或整份文件一起重算，
    下面关于 facts_rescanned / 旧列哈希不变的断言就会红。
    """

    # 必须用**完整**文件：截断分片按设计不复用（否则测的是 partial 规则而不是列增量）。
    mini = _mini_manifest(tmp_path, SLICE)
    out = tmp_path / "cache"
    first = pc.build(mini, out, candidates=("chain_path_value",), verbose=False)
    chain_column = first["candidates"]["chain_path_value"]["columns"][0]["sha256"]
    shard_sha = first["files"][0]["shard_sha256"]
    second = pc.build(mini, out, candidates=("chain_path_value", "meld_opportunity_cost"),
                      verbose=False)
    assert second["facts"]["digest"] == first["facts"]["digest"]
    assert second["files"][0]["shard_sha256"] == shard_sha
    assert second["build"]["per_file"][0]["facts_rescanned"] is False
    assert second["build"]["per_file"][0]["columns_rebuilt"] == ["meld_opportunity_cost"]
    assert (second["candidates"]["chain_path_value"]["columns"][0]["sha256"]
            == chain_column)
    assert len(second["candidates"]["meld_opportunity_cost"]["columns"]) == 1
    result = pc.verify(out, verbose=False)
    assert result["ok"] is True, result["problems"]


def test_era_comparable_scope_drops_legacy_mismatch_windows(tmp_path: Path) -> None:
    """按记录时代分层：legacy 时代的 legal mismatch 窗口不进逐类账分母，单列条数（A 裁决）。"""

    records = [
        {"i": 0, "l": 1, "k": "w1", "s": pc.STATUS["scored"], "lg": pc.LEGAL["mismatch"],
         "in": ["chain.open"], "ol": ["discard:1w"], "rk": ["discard:2w"]},
        {"i": 0, "l": 2, "k": "w2", "s": pc.STATUS["scored"], "lg": pc.LEGAL["match"],
         "in": ["chain.open"]},
    ]
    # legacy 时代的判据 = **记录侧自述版本**与本次重算版本不同（直接证据）。
    legacy = _write_cache(tmp_path, records, rulesets=("hangma-mvp-v4-youcai-baotou",))
    payload = pc.aggregate(legacy, verbose=False)
    assert payload["record_era_layering"]["era_incomparable_windows"] == 1
    assert payload["record_era_layering"]["by_file"]["a/decisions.jsonl"]["era"] == \
        pc.ERA_LEGACY
    assert payload["record_era_layering"]["by_file"]["a/decisions.jsonl"][
        "era_basis"].startswith("recorded-ruleset-version")
    assert payload["class_windows"]["chain.open"] == 2
    assert payload["class_windows_era_comparable"]["chain.open"] == 1
    evaluation = pc.evaluation_from_cache(legacy, class_scope="era_comparable")
    assert evaluation["panel"]["class_scope_excluded_windows"] == 1
    assert [record["window"] for record in evaluation["records"]] == ["w2"]
    everything = pc.evaluation_from_cache(legacy, class_scope="all")
    assert everything["panel"]["class_scope_excluded_windows"] == 0
    assert len(everything["records"]) == 2

def test_era_falls_back_to_session_timestamp_without_versions(tmp_path: Path) -> None:
    """没有记录侧版本串时退回会话时间戳（不猜、不默认 current）。"""

    records = [{"i": 0, "l": 1, "k": "w1", "s": pc.STATUS["scored"],
                "lg": pc.LEGAL["mismatch"], "in": ["chain.open"]}]
    cache = _write_cache(tmp_path, records, rulesets=(), era_ts=pc.ERA_LEGACY)
    payload = pc.aggregate(cache, verbose=False)
    detail = payload["record_era_layering"]["by_file"]["a/decisions.jsonl"]
    assert detail["era"] == pc.ERA_LEGACY
    assert detail["era_basis"] == "session-timestamp-fallback"


def test_resolve_era_prefers_recorded_version_over_timestamp() -> None:
    """版本串优先：09-09 的会话时间戳早于提交作者时间，但记录已声明 v10 ⇒ current。"""

    era, basis = pc.resolve_era(("hangma-mvp-v10-public-counts",),
                                "hangma-mvp-v10-public-counts", pc.ERA_LEGACY)
    assert era == pc.ERA_CURRENT
    assert basis.startswith("recorded-ruleset-version==recompute")
    era, basis = pc.resolve_era(("hangma-mvp-v4-youcai-baotou",),
                                "hangma-mvp-v10-public-counts", pc.ERA_CURRENT)
    assert era == pc.ERA_LEGACY
