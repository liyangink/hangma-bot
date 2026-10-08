"""canonical 面板的**面板自洽核对明细**：本地规则重算 vs 记录落盘合法候选的 72 处不一致。

背景：canonical 覆盖账的 `legal_reconciliation` = match 337,946 / mismatch 72（0.02%）。
本探针回答"这 72 处是什么"，而不是把它们当噪声：
- 落在哪些会话/日期；
- 是否与「本人手上有财神」（`you_cai_bi_kao` 面板声明的开关只有在**手留财神**时才改变合法胡候选）
  或链 / 爆头 / 抓打圈状态相关；
- 逐条给出 recorded 与 local 的动作键差异（有界样本）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import collections
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(TOOLS))

spec = importlib.util.spec_from_file_location("sitin_scenario_classes",
                                              _project_file(_PROJECT_ROOT, TOOLS / "sitin_scenario_classes.py"))
sc = importlib.util.module_from_spec(spec)
sys.modules["sitin_scenario_classes"] = sc
assert spec.loader is not None
spec.loader.exec_module(sc)

from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402

PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/raw/54-legal-mismatch.json')
RULESET = "hangma-mvp-v10-public-counts"
SAMPLE_CAP = 20


def main() -> int:
    manifest = json.loads(PANEL.read_text(encoding="utf-8"))
    codec = build_decision_codec()
    decode_request = codec["decode_request"]
    rules = HangmaRules(RuleConfig(ruleset_version=RULESET, base_score=1,
                                   you_cai_bi_kao=False))
    counters = collections.Counter()
    by_session = collections.Counter()
    samples: list = []
    started = time.time()
    for item in manifest["files"]:
        rel = item["path"]
        session = rel.split("/")[2]
        day = rel.split("/")[4][:8]
        with (_project_file(_PROJECT_ROOT, ROOT / rel)).open(encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                payload = row.get("request")
                if not isinstance(payload, dict):
                    continue
                counters["rows"] += 1
                try:
                    recorded = decode_request(payload)
                except Exception:
                    counters["undecodable"] += 1
                    continue
                filled_row = sc.normalize_record_layer(row, "filled")
                try:
                    filled = decode_request(filled_row["request"])
                except Exception:
                    filled = recorded
                recorded_keys = {entry.get("action_key")
                                 for entry in ((payload.get("rules") or {}).get(
                                     "legal_candidates") or ())}
                for view, decoded in (("raw", recorded), ("filled", filled)):
                    try:
                        analysis = rules.analyze(decoded.observation)
                    except Exception:
                        counters[view + "_analyze_error"] += 1
                        continue
                    local_keys = {candidate.action_key
                                  for candidate in analysis.legal_candidates}
                    if recorded_keys == local_keys:
                        counters[view + "_match"] += 1
                        continue
                    counters[view + "_mismatch"] += 1
                    state = decoded.observation.rule_state
                    holds_wealth = any(tile.code == state.wealth_god.code
                                       for tile in decoded.observation.my_hand)
                    counters[view + ("_holds_wealth" if holds_wealth else "_no_wealth")] += 1
                    if state.chain_count > 0:
                        counters[view + "_chain_nonzero"] += 1
                    if state.baotou:
                        counters[view + "_baotou"] += 1
                    if view == "filled" and len(samples) < SAMPLE_CAP:
                        by_session[session] += 1
                        samples.append({
                            "file": rel, "day": day, "session": session, "line": lineno,
                            "decision_id": row.get("decision_id"),
                            "recorded_keys": sorted(recorded_keys),
                            "local_keys": sorted(local_keys),
                            "only_recorded": sorted(recorded_keys - local_keys),
                            "only_local": sorted(local_keys - recorded_keys),
                            "holds_wealth_god": holds_wealth,
                            "chain_count": state.chain_count,
                            "chain_piao": decoded.observation.chain_piao,
                            "baotou": state.baotou,
                            "catch_play": state.catch_play,
                            "remaining_tile_count": getattr(
                                decoded.observation, "remaining_tile_count", None),
                        })
    result = {
        "schema": "sitin-legal-mismatch/1",
        "panel_id": manifest.get("panel_id"),
        "panel_fingerprint": manifest.get("fingerprint"),
        "counters": dict(counters),
        "mismatch_by_session_top": by_session.most_common(10),
        "samples": samples,
        "elapsed_sec": round(time.time() - started, 1),
        "note": ("mismatch 是**面板参数**层面的信号（规则配置是否与产生记录时一致），"
                 "不是候选行为；引用时必须与面板 id 一起给。"),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # **逐键兜底**：某类窗口一个都没有时该键不存在，直接 **counters 会让 format 报 KeyError。
    summary = {key: counters.get(key, 0) for key in (
        "rows", "undecodable", "raw_match", "raw_mismatch", "filled_match", "filled_mismatch",
        "raw_holds_wealth", "raw_no_wealth", "raw_chain_nonzero", "raw_baotou",
        "filled_holds_wealth", "filled_no_wealth", "filled_chain_nonzero", "filled_baotou")}
    print("行 {rows}｜filled 视图 match {filled_match} / mismatch {filled_mismatch}"
          "（其中手上有财神 {filled_holds_wealth}、链非零 {filled_chain_nonzero}、爆头 {filled_baotou}）".format(
              **summary))
    print("raw 视图 mismatch:", counters["raw_mismatch"])
    print("按会话 top:", by_session.most_common(5))
    if samples:
        first = samples[0]
        print("样例：only_recorded={0} only_local={1} holds_wealth={2}".format(
            first["only_recorded"], first["only_local"], first["holds_wealth_god"]))
    print("耗时 {0}s".format(result["elapsed_sec"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
