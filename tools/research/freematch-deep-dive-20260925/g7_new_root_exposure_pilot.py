#!/usr/bin/env python3
"""G7 新牌山根结果盲工程试跑：频率、身份和三摸规则计算成本。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
import g1_timing_natural_exposure as g1  # noqa: E402
import g7_g6_overlap as overlap  # noqa: E402
import g7_natural_three_draw_exposure as g7  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-new-root-exposure-pilot-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G7-NEW-ROOT-EXPOSURE-PILOT-PREREG-2026-09-27.md')
PANEL_SEED = 2026102901
MIXES = ("H", "M")
ROOTS = (101, 102, 103, 104)
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def sources():
    return [{"mix": mix, "root_index": root, "focal_seat": seat,
             "source_root_id": f"{mix}:g7:{PANEL_SEED}:r{root:03d}",
             "source_id": f"{mix}:g7:{PANEL_SEED}:r{root:03d}:s{seat}"}
            for mix in MIXES for root in ROOTS for seat in SEATS]


def _path(source):
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (source["source_id"].replace(":", "-") + ".json"))


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("G7 试跑目录已存在，拒绝覆盖")
    parent = g1.p83.parent_source()
    if hashlib.sha256(parent.encode()).hexdigest() != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("冻结父代摘要不符")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    frozen = sources()
    authorization = g1.p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g7-new-root-exposure-pilot-20260927",
        accounts={"tables_full": len(frozen) * TABLES_PER_SOURCE},
        issued_by="lead", issued_at_utc=g1.p83.search.utc_now(), legacy_alias=False,
    )
    authorization.update({"scope": "64 桌结果盲自然机会与计算成本试跑",
                          "max_model_calls": 0, "confirmation_roots": 0})
    _write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    _write(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "g7-new-root-sources/1", "sources": frozen})
    tracked = [Path(__file__), PREREG, g1.CONTRACT, g1.PARENT,
               Path(g7.__file__), Path(overlap.__file__),
               Path(g1.p83.natural.__file__), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
               _project_file(_PROJECT_ROOT, OUT / "sources.json")]
    _write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g7-new-root-pilot-manifest/1",
        "created_at_utc": g1.p83.search.utc_now(),
        "runtime": g1.p83.guard.capture(source_paths=tracked),
        "contract_sha256": _sha(g1.CONTRACT), "prereg_sha256": _sha(PREREG),
        "parent_source_sha256": g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "panel_seed": PANEL_SEED, "source_units": len(frozen),
        "planned_tables": len(frozen) * TABLES_PER_SOURCE,
        "sample_per_source": 2, "outcome_blind": True,
        "release_eligible": False,
    })
    print(json.dumps({"prepared_sources": len(frozen), "planned_tables": 64}))


def _verify():
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if (_sha(g1.CONTRACT) != manifest["contract_sha256"]
            or _sha(PREREG) != manifest["prereg_sha256"]
            or manifest["parent_source_sha256"] != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("冻结合同、预登记或父代漂移")
    g1.p83.guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("来源清单漂移")
    return manifest, frozen


def _audit(requests, source, parent):
    scorer = ActionValueScorer("g7-pilot-replay-" + source["source_id"], parent)
    counters = Counter()
    options = []
    for request in requests:
        counters["focal_requests"] += 1
        obs = request.observation
        if obs.phase != "draw":
            continue
        counters["focal_draw_requests"] += 1
        view = build_scoring_view(request)
        scored = scorer.score(view)
        if scored.status != "SCORED":
            raise ValueError("冻结父代在自然窗口弃权")
        ranked = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
        raw = decision_request_to_json(request)
        planned = {"candidates": [{"action_key": item.action_key,
                                   "total_score": item.score} for item in ranked]}
        pair = g7._eligible(raw, planned)
        if pair is None:
            continue
        counters["g7_a_b_eligible"] += 1
        a, b, shanten, whites = pair
        useful_a = overlap._useful_distribution(raw, a)
        useful_b = overlap._useful_distribution(raw, b)
        if useful_a is None or useful_b is None:
            counters["unknown_full_useful_distribution"] += 1
            continue
        if useful_a != useful_b:
            continue
        counters["same_full_useful_distribution"] += 1
        key = (obs.game_id, obs.round_no, request.trigger_seq)
        options.append({"group": source["mix"], "room": "offline-natural",
                        "game_id": key[0], "round_no": key[1],
                        "trigger_seq": key[2], "hash": g7._digest(key),
                        "a": a, "b": b, "shanten": shanten, "whites": whites,
                        "request": raw})
    selected = sorted(options, key=lambda row: row["hash"])[:2]
    results = []
    for row in selected:
        try:
            evaluated = g7._evaluate(row)
        except (ValueError, KeyError) as exc:
            counters["invalid_rule_proxy"] += 1
            results.append({"game_id": row["game_id"], "round_no": row["round_no"],
                            "trigger_seq": row["trigger_seq"],
                            "invalid_rule_proxy": type(exc).__name__ + ": " + str(exc)})
            continue
        counters["evaluated"] += 1
        if evaluated["delta_2"] == 0:
            counters["two_draw_tie"] += 1
            counters["two_tie_three_" + ("positive" if evaluated["delta_3"] > 0 else
                                        "negative" if evaluated["delta_3"] < 0 else
                                        "zero")] += 1
        results.append(evaluated)
    return {"counts": dict(counters), "selected": results}


def _run_source(source):
    contract = json.loads(g1.CONTRACT.read_text(encoding="utf-8"))
    parent = g1.p83.parent_source()
    plans = g1.p83.natural.build_seat_stage_plans(
        contract=contract, opponent=source["mix"], root_index=source["root_index"],
        focal_seat=source["focal_seat"], panel_seed=PANEL_SEED,
    )
    requests = []
    name = "g7-pilot-" + source["source_id"]
    stage = g1.p83.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer(name, parent),
        opponent_policies=contract["panel"]["opponent_scenarios"][source["mix"]][
            "opponent_policies"],
        versions_block=g1.p83.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=g1.p83.LIMITS, decision_observer=requests.append,
    )
    if stage.get("status") != "complete" or len(stage.get("tables") or []) != TABLES_PER_SOURCE:
        raise RuntimeError(stage.get("error") or "自然阶段未完成")
    focal_ids = []
    for plan, table in zip(plans, stage["tables"]):
        seat = plan.seats().index(g1.p83.natural.FOCAL_PARTICIPANT)
        ids = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
        expected = "action_value_v1:" + name
        if len(ids) != 4 or ids[seat] != expected:
            raise RuntimeError("焦点策略身份与冻结父代不符")
        focal_ids.append(expected)
    return {"source": source, "status": "complete", "tables": TABLES_PER_SOURCE,
            "focal_policy_ids": focal_ids,
            "audit": _audit(requests, source, parent)}


def run() -> None:
    manifest, frozen = _verify()
    auth = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    g1.p83.natural.require_authorization(auth)
    book = g1.p83.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=g1.p83.search.av_ledger_budgets_from_authorization(auth),
    )
    complete = 0
    for source in frozen:
        path = _path(source)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("已存来源不完整")
            complete += TABLES_PER_SOURCE
            continue
        reservation = book.reserve(
            step_id="g7:pilot:" + source["source_id"], account="tables_full",
            amount=TABLES_PER_SOURCE, note="新根结果盲潜在牌形频率工程试跑",
        )
        try:
            result = _run_source(source)
            _write(path, result)
            book.settle(reservation, actual=TABLES_PER_SOURCE, note="两桌完成且焦点身份一致")
            complete += TABLES_PER_SOURCE
        except BaseException:
            book.settle(reservation, usage_unknown=True, note="来源异常，保守计费")
            raise
        if complete % 8 == 0 or complete == manifest["planned_tables"]:
            print(json.dumps({"completed_tables": complete,
                              "planned_tables": manifest["planned_tables"]}), flush=True)
    _write(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "g7-new-root-pilot-run/1", "completed_tables": complete,
        "planned_tables": manifest["planned_tables"], "spent": book.account_summary(),
        "outcome_labels_opened": False,
    })


def analyze() -> None:
    manifest, frozen = _verify()
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("结果已冻结，拒绝覆盖")
    if not (_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).exists():
        raise ValueError("未完成自然阶段")
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("64 桌未跑满")
    counts = defaultdict(Counter)
    roots = defaultdict(lambda: defaultdict(set))
    runtime = []
    rows = []
    for source in frozen:
        document = json.loads(_path(source).read_text(encoding="utf-8"))
        if document["status"] != "complete" or len(document["focal_policy_ids"]) != 2:
            raise ValueError("来源身份或桌数不完整")
        mix = source["mix"]
        counts[mix].update(document["audit"]["counts"])
        for item in document["audit"]["selected"]:
            if "invalid_rule_proxy" in item:
                continue
            item = dict(item, source=source)
            rows.append(item)
            runtime.append(item["elapsed_ms"])
            if item["delta_2"] == 0:
                category = ("positive" if item["delta_3"] > 0 else
                            "negative" if item["delta_3"] < 0 else "zero")
                roots[mix][category].add(source["source_root_id"])
    ordered = sorted(runtime)
    def pct(q):
        if not ordered:
            return None
        return ordered[min(len(ordered)-1, int(q * (len(ordered)-1)))]
    output = {"schema": "g7-new-root-pilot-result/1",
              "parent_source_sha256": manifest["parent_source_sha256"],
              "planned_tables": manifest["planned_tables"],
              "counts": {mix: dict(counts[mix]) for mix in MIXES},
              "independent_roots": {mix: {name: len(values) for name, values in roots[mix].items()}
                                    for mix in MIXES},
              "rule_proxy_runtime_ms": {"count": len(ordered),
                                        "p50": statistics.median(ordered) if ordered else None,
                                        "p95": pct(0.95), "max": max(ordered) if ordered else None},
              "rows": rows, "outcome_labels_opened": False,
              "release_eligible": False}
    _write(_project_file(_PROJECT_ROOT, OUT / "result.json"), output)
    print(json.dumps({"counts": output["counts"],
                      "independent_roots": output["independent_roots"],
                      "runtime_ms": output["rule_proxy_runtime_ms"]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "analyze": analyze}[args.command]()


if __name__ == "__main__":
    main()
