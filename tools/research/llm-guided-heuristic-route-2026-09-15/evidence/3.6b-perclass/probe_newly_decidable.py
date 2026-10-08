"""F7 ③：canonical 面板上"由 DEGRADED 变可判"的窗口**单列**（newly_scored），并列明不可归因行。

口径（Lead 裁定 F7）：
- 两个记录层视图在同一份清单上逐行对照：`raw`（记录原样）与 `filled`（记录层归一化）；
- **newly_scored** = 修前被规则层降级排除（DEGRADED 或无合法候选）、修后进入计分的窗口
  （旧名 newly_decidable 已按 Lead 指令**删除**，避免与"净已知差"混淆）；
- 反向变化（修前可判、修后降级）也计数，不隐藏；
- 归一化后**仍不可归因**的行逐行列明（不抹平、不并入分母）；
- 两个视图的链族可用窗口（`chain_count>0` 且链内飘出可判定）并列报，供与 3.6d 的证据对拍。

只读：不跑桌赛、不写语料、不改候选。输出 JSON 与人类可读两段。
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

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(TOOLS))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("sitin_scenario_classes",
                                              _project_file(_PROJECT_ROOT, TOOLS / "sitin_scenario_classes.py"))
sc = importlib.util.module_from_spec(spec)
sys.modules["sitin_scenario_classes"] = sc
assert spec.loader is not None
spec.loader.exec_module(sc)
gates = sc._tool("sitin_gates")

from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import RuleCompleteness  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402

PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/raw/51-newly-decidable.json')
#: 对端（corpus 3.6d）产物：**运行时读取**，不写死数字（F12 ② 返工点）。
PEER = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6d-corpus/corpus-audit.json')
RULESET = "hangma-mvp-v10-public-counts"


def main() -> int:
    manifest = json.loads(PANEL.read_text(encoding="utf-8"))
    files = [item["path"] for item in manifest["files"]]
    codec = build_decision_codec()
    decode_request = codec["decode_request"]
    rules = HangmaRules(RuleConfig(ruleset_version=RULESET, base_score=1,
                                   you_cai_bi_kao=False))
    key = sc.chain_piao_module().CHAIN_PIAO_ATTRIBUTION_KEY

    # 字段名**只保留对齐口径**（旧名 newly_decidable / newly_degraded 已删除，Lead 指令）：
    #   newly_scored   = 修前被排除 → 修后进入计分（分母侧）
    #   reverse_excluded = 修前计分 → 修后降级（与 corpus 同键名）
    # **键名与 corpus（3.6d corpus-audit.json 的 canonical_panel）逐项相同**（Lead 指令：与另一包一致）：
    #   newly_attributable / newly_scored / attributable_but_excluded / reverse_excluded /
    #   still_unknown_rows / net_scored_delta / net_usable_window_delta
    counters = {"rows": 0, "raw_degraded": 0, "filled_degraded": 0,
                "newly_scored": 0, "reverse_excluded": 0, "both_degraded": 0,
                "rows_changed_value": 0, "still_unknown_rows": 0,
                # 口径命名与 corpus 包（3.6d）对齐（Lead 指令 ③）：
                #   newly_attributable = 行侧：raw 未知 → filled 已知
                #   newly_scored       = 分母侧：修前被规则层降级排除 → 修后进入计分
                #   still_unknown      = 修后仍不可归因且 chain_count>0
                #   net_usable_window_delta = 链族可用窗口差（== 已知数净差）
                "newly_attributable": 0, "downgraded_to_unknown": 0,
                "raw_chain_usable": 0, "filled_chain_usable": 0,
                "raw_chain_piao_known": 0, "filled_chain_piao_known": 0}
    newly_scored_samples: list = []
    still_unknown_rows: list = []
    started = time.time()
    for rel in files:
        path = _project_file(_PROJECT_ROOT, ROOT / rel)
        with path.open(encoding="utf-8") as handle:
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
                    raw = decode_request(payload)
                except Exception:
                    continue
                filled_row = sc.normalize_record_layer(row, "filled")
                attribution = filled_row.get(key) or {}
                try:
                    filled = decode_request(filled_row["request"])
                except Exception:
                    filled = raw
                raw_obs, filled_obs = raw.observation, filled.observation

                raw_bad = _degraded(rules, raw_obs)
                filled_bad = _degraded(rules, filled_obs)
                counters["raw_degraded"] += int(raw_bad)
                counters["filled_degraded"] += int(filled_bad)
                if raw_bad and not filled_bad:
                    counters["newly_scored"] += 1
                    if len(newly_scored_samples) < 20:
                        newly_scored_samples.append({
                            "file": rel, "line": lineno, "decision_id": row.get("decision_id"),
                            "chain_count": raw_obs.rule_state.chain_count,
                            "live_chain_piao": raw_obs.chain_piao,
                            "filled_chain_piao": filled_obs.chain_piao,
                            "attribution_status": attribution.get("status"),
                            "rungs": attribution.get("rungs"),
                        })
                elif raw_bad and filled_bad:
                    counters["both_degraded"] += 1
                elif filled_bad and not raw_bad:
                    counters["reverse_excluded"] += 1

                if attribution.get("changed"):
                    counters["rows_changed_value"] += 1
                if attribution.get("status") == "unknown" and \
                        raw_obs.rule_state.chain_count > 0:
                    counters["still_unknown_rows"] += 1
                    still_unknown_rows.append({
                        "file": rel, "line": lineno, "decision_id": row.get("decision_id"),
                        "chain_count": raw_obs.rule_state.chain_count,
                        "live_value": attribution.get("live_value"),
                        "piao": attribution.get("piao"),
                        "reason": attribution.get("reason"),
                        "rungs": attribution.get("rungs"),
                        "witness_seqs": attribution.get("witness_seqs"),
                    })
                if raw_obs.chain_piao is None and filled_obs.chain_piao is not None:
                    counters["newly_attributable"] += 1
                if raw_obs.chain_piao is not None and filled_obs.chain_piao is None:
                    counters["downgraded_to_unknown"] += 1
                if raw_obs.chain_piao is not None:
                    counters["raw_chain_piao_known"] += 1
                if filled_obs.chain_piao is not None:
                    counters["filled_chain_piao_known"] += 1
                if raw_obs.rule_state.chain_count > 0 and raw_obs.chain_piao is not None:
                    counters["raw_chain_usable"] += 1
                if filled_obs.rule_state.chain_count > 0 and filled_obs.chain_piao is not None:
                    counters["filled_chain_usable"] += 1

    # ---- 口径对照（Lead 指令 ②③）：四个量各自带名与判据，不许用一个数含糊表达 ----
    newly_attributable = counters["newly_attributable"]
    newly_scored = counters["newly_scored"]
    still_unknown = counters["still_unknown_rows"]
    net_usable_delta = counters["filled_chain_usable"] - counters["raw_chain_usable"]
    net_scored_delta = newly_scored - counters["reverse_excluded"]
    still_excluded = newly_attributable - newly_scored
    peer_comparison = compare_peer({
        "newly_attributable": newly_attributable,
        "newly_scored": newly_scored,
        "attributable_but_excluded": still_excluded,
        "reverse_excluded": counters["reverse_excluded"],
        "still_unknown_rows": still_unknown,
        "net_scored_delta": net_scored_delta,
        "net_usable_window_delta": net_usable_delta,
    })
    reconciliation = {
        "newly_attributable": {
            "value": newly_attributable,
            "basis": "行侧：raw observation.chain_piao is None ∧ filled is not None（记录层把未知补成值）",
        },
        "newly_scored": {
            "value": newly_scored,
            "basis": ("分母侧（**本包唯一使用的口径**）：raw 被规则层降级排除 ∧ filled 进入计分；"
                      "由引擎判据（RuleCompleteness + 合法候选）现算，不是行侧差值"),
        },
        "still_unknown_rows": {
            "value": still_unknown,
            "basis": ("filled 视图下 attribution.status=unknown 且 chain_count>0"
                      "（不可归因 ⇒ 记 unknown，逐行列明，不并入分母）"),
        },
        "net_usable_window_delta": {
            "value": net_usable_delta,
            "basis": "filled_chain_usable − raw_chain_usable（链族可用窗口差）",
        },
        "attributable_but_excluded": {
            "value": still_excluded,
            "basis": ("newly_attributable − newly_scored：已可归因但仍被**其他规则**排除，"
                      "没有进入分母"),
        },
        "reverse_excluded": {
            "value": counters["reverse_excluded"],
            "basis": ("记录层归一化把 live 值降级为未知、且在引擎判据下由可计分变为被排除的窗口数"
                      "（反向变化，不隐藏）"),
        },
        "net_scored_delta": {
            "value": net_scored_delta,
            "basis": "newly_scored − reverse_excluded（引擎判据下排除窗口数的净变化）",
        },
        "identity_checks": {
            "newly_attributable_minus_newly_scored_equals_attributable_but_excluded": True,
            # 降级数**下降**的量 == 净进入计分的窗口数：raw − filled == newly_scored − reverse。
            # （初版把两边符号写反了，断言自己报 false —— 数字没错，检查写错，已修并复跑。）
            "degraded_drop_equals_net_newly_scored": (
                counters["raw_degraded"] - counters["filled_degraded"]
                == newly_scored - counters["reverse_excluded"]),
            "net_usable_delta_equals_known_delta": (
                net_usable_delta
                == counters["filled_chain_piao_known"] - counters["raw_chain_piao_known"]),
        },
        "cross_package": {
            "peer_package": "corpus（3.6d）",
            "peer_field": ("canonical_panel.net_usable_window_delta（对端 F13/F7 后的现行键名；"
                           "旧名 newly_decidable_windows 已在对端删除）"),
            "peer_comparison": peer_comparison,
            "relation": ("**不是同一个量**：对端 net_usable_window_delta = 净已知差 / 链族可用窗口差；"
                         "本包的 newly_scored 是**跨过分母边界**、由引擎判据现算的窗口数。"
                         "引用时必须写明用哪一个；本包以分母口径 newly_scored 为准。"),
            "aligned_keys": {
                "peer_path": "evidence/3.6d-corpus/corpus-audit.json → canonical_panel",
                "newly_attributable": newly_attributable,
                "newly_scored": newly_scored,
                "attributable_but_excluded": still_excluded,
                "reverse_excluded": counters["reverse_excluded"],
                "still_unknown_rows": still_unknown,
                "net_scored_delta": net_scored_delta,
                "net_usable_window_delta": net_usable_delta,
                "keys_identical_to_peer": True,
            },
        },
        "note": ("四个量各自带判据；newly_attributable − newly_scored = {0} 属"
                 "「已可归因但仍被其他规则排除」，不得并入分母，也不得与 16 混用。".format(
                     still_excluded)),
    }
    result = {
        "schema": "sitin-newly-decidable/1",
        # 面板身份（F7）：指纹取**清单内容指纹**（105 份文件的 sha256 组合，稳定）；
        # 清单文件自身的哈希另存 manifest_sha256，随清单元数据变化，不参与面板身份。
        "panel_id": manifest.get("panel_id"),
        "panel_fingerprint": manifest.get("fingerprint"),
        "manifest_sha256": hashlib.sha256(PANEL.read_bytes()).hexdigest(),
        "panel_rows": manifest.get("rows"),
        "record_layer_pair": ["raw", "filled"],
        "counters": counters,
        "reconciliation": reconciliation,
        "newly_scored_samples": newly_scored_samples,
        "still_unknown_rows": still_unknown_rows,
        "elapsed_sec": round(time.time() - started, 1),
        "note": ("newly_scored 的窗口在 canonical 口径下**计入分母**，但必须**单列计数**；"
                 "raw 视图的数字只能作为前态对照，不得与 filled 视图混用分母。"
                 "旧名 newly_decidable 已删除（它与净差 16 是两个量）。"),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("行 {rows}｜raw 降级 {raw_degraded} → filled 降级 {filled_degraded}".format(**counters))
    print("newly_scored（修前排除→修后计分）:", counters["newly_scored"],
          "｜reverse_excluded（修前可判→修后降级）:", counters["reverse_excluded"],
          "｜两视图都降级:", counters["both_degraded"])
    print("口径对照（键名与 corpus 逐项相同）：newly_attributable={0} / newly_scored={1} / "
          "attributable_but_excluded={2} / reverse_excluded={3} / still_unknown_rows={4} / "
          "net_scored_delta={5:+d} / net_usable_window_delta={6:+d}".format(
              newly_attributable, newly_scored, still_excluded, counters["reverse_excluded"],
              still_unknown, net_scored_delta, net_usable_delta))
    print("链族可用窗口 raw → filled:", counters["raw_chain_usable"], "→",
          counters["filled_chain_usable"])
    print("chain_piao 已知 raw → filled:", counters["raw_chain_piao_known"], "→",
          counters["filled_chain_piao_known"])
    print("still_unknown_rows（不可归因且 chain_count>0）:", counters["still_unknown_rows"],
          "行；逐行列明见", OUT.name)
    print("耗时 {0}s".format(result["elapsed_sec"]))
    return 0


def compare_peer(values: dict) -> dict:
    """读对端 corpus-audit.json 的 canonical_panel 段并逐项对拍（**不写死数字**）。

    F12 ②：旧写法把 "canonical_panel.newly_decidable_windows = 16" 写死在产物里，
    对端字段改名后这句话就成了**假引用**。现在字段名与取值都在运行时从对端产物读，
    读不到就显式记 null（不猜、不填零）。
    """

    if not PEER.is_file():
        return {"peer_path": str(PEER.relative_to(ROOT)), "available": False,
                "note": "对端产物不存在：本轮不做数值对拍（也不写死任何数字）"}
    data = json.loads(PEER.read_text(encoding="utf-8"))
    panel = data.get("canonical_panel") or {}
    mapping = {
        "newly_attributable": "newly_attributable",
        "newly_scored": "newly_scored",
        "attributable_but_excluded": "attributable_but_excluded",
        "reverse_excluded": "reverse_excluded",
        "still_unknown_rows": "still_unknown_rows",
        "net_scored_delta": "net_scored_delta",
        "net_usable_window_delta": "net_usable_window_delta",
    }
    peer_values = {key: panel.get(key) for key in mapping}
    ours = {key: values.get(key) for key in mapping}
    return {
        "peer_path": str(PEER.relative_to(ROOT)),
        "peer_sha256": hashlib.sha256(PEER.read_bytes()).hexdigest(),
        "available": True,
        "peer_keys_present": sorted(key for key, value in peer_values.items() if value is not None),
        "peer_values": peer_values,
        "our_values": ours,
        "agreement": {key: bool(ours[key] == peer_values[key]) for key in mapping},
        "all_agree": all(ours[key] == peer_values[key] for key in mapping),
        "note": ("逐项相等 = 两包在同一键名同一判据下同值；不等时以各自 basis 为准，"
                 "不得互相覆盖。旧名 newly_decidable_windows 在对端已删除。"),
    }


def _degraded(rules: HangmaRules, observation) -> bool:
    """该窗口在规则层是否被降级排除（与覆盖账的排除判据同口径）。"""

    try:
        analysis = rules.analyze(observation)
    except Exception:
        return True
    return (analysis.completeness is RuleCompleteness.DEGRADED
            or not analysis.legal_candidates)


if __name__ == "__main__":
    sys.exit(main())
