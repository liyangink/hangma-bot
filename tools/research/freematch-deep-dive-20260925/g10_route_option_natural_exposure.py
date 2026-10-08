#!/usr/bin/env python3
"""G10 新 H/M 牌山根的结果盲路线动作自然暴露。"""

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
import sys


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
import g1_timing_natural_exposure as g1  # noqa: E402
import g10_route_option_screen as screen  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-natural-exposure-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G10-ROUTE-OPTION-ACTION-VALUE-PREREG-2026-09-27.md')
SCREEN = screen.OUT
PANEL_SEED = 2026110501
MIXES = ("H", "M")
ROOTS = tuple(range(1, 25))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: object) -> str:
    """按确定性 JSON 字节冻结一个动作前请求，不含未来结果。"""

    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def sources() -> list[dict]:
    """H/M 各二十四独立根，四座轮换，每座自然完成两张桌赛。"""

    return [{"mix": mix, "root_index": root, "focal_seat": seat,
             "source_root_id": f"{mix}:g10:{PANEL_SEED}:r{root:03d}",
             "source_id": f"{mix}:g10:{PANEL_SEED}:r{root:03d}:s{seat}"}
            for mix in MIXES for root in ROOTS for seat in SEATS]


def _path(source: dict) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (source["source_id"].replace(":", "-") + ".json"))


def prepare() -> None:
    """在看任何新根桌分前冻结来源、父代、规则与暴露程序。"""

    if OUT.exists():
        raise SystemExit("G10 自然暴露目录已存在，拒绝覆盖")
    parent = g1.p83.parent_source()
    if hashlib.sha256(parent.encode()).hexdigest() != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("冻结 R18 v2 父代源码摘要漂移")
    prior = json.loads(SCREEN.read_text(encoding="utf-8"))
    if (prior["exposure_gate_passed"] is not True or prior["outcome_blind"] is not True
            or prior["source_parent_sha256"] != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("G10 官方动作暴露门或父代身份不符")
    frozen = sources()
    if len(frozen) != 192 or len({row["source_root_id"] for row in frozen}) != 48:
        raise ValueError("新根、四座来源数量不符")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    authorization = g1.p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g10-route-option-natural-exposure-20260927",
        accounts={"tables_full": len(frozen) * TABLES_PER_SOURCE},
        issued_by="lead", issued_at_utc=g1.p83.search.utc_now(), legacy_alias=False,
    )
    authorization.update({"scope": "G10 H/M 新根四座 384 张结果盲自然桌",
                          "max_model_calls": 0, "confirmation_roots": 0})
    _write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    _write(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "g10-route-option-sources/1", "sources": frozen})
    closure = [Path(__file__), PREREG, SCREEN, Path(screen.__file__),
               g1.CONTRACT, g1.PARENT, Path(g1.__file__),
               Path(g1.p83.natural.__file__), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
               _project_file(_PROJECT_ROOT, OUT / "sources.json")]
    _write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g10-route-option-natural-exposure-manifest/1",
        "created_at_utc": g1.p83.search.utc_now(),
        "runtime": g1.p83.guard.capture(source_paths=closure),
        "contract_sha256": _sha(g1.CONTRACT), "prereg_sha256": _sha(PREREG),
        "screen_sha256": _sha(SCREEN),
        "parent_source_sha256": g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "panel_seed": PANEL_SEED, "source_units": len(frozen),
        "planned_tables": len(frozen) * TABLES_PER_SOURCE,
        "tables_per_source": TABLES_PER_SOURCE,
        "outcome_blind": True, "release_eligible": False,
    })
    print(json.dumps({"sources": len(frozen), "independent_roots": 48,
                      "planned_tables": len(frozen) * TABLES_PER_SOURCE}))


def _verify() -> tuple[dict, list[dict]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if (_sha(g1.CONTRACT) != manifest["contract_sha256"]
            or _sha(PREREG) != manifest["prereg_sha256"]
            or _sha(SCREEN) != manifest["screen_sha256"]
            or manifest["parent_source_sha256"] != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("冻结合同、筛查、预登记或父代摘要漂移")
    g1.p83.guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("自然来源清单漂移")
    return manifest, frozen


def _table_no(game_id: str) -> int:
    """自然阶段的桌编号仅用于同一来源内固定动作先后。"""

    suffix = game_id.rsplit("-t", 1)
    if len(suffix) != 2 or not suffix[1].isdigit():
        raise ValueError("自然阶段 game_id 缺桌号")
    return int(suffix[1])


def _eligible(request, scorer: ActionValueScorer) -> tuple[dict | None, str]:
    """与官方结果盲筛查同一规则谓词，只输出动作前公开事实。"""

    observation = request.observation
    if observation.phase != "draw":
        return None, "not_draw"
    view = build_scoring_view(request)
    scored = scorer.score(view)
    if scored.status != "SCORED":
        return None, "parent_unscored"
    ranked = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if not ranked or not ranked[0].action_key.startswith("discard:"):
        return None, "parent_not_discard"
    raw = decision_request_to_json(request)
    legal = {item["action_key"]: item.get("facts") or {} for item in
             (raw.get("rules") or {}).get("legal_candidates") or []}
    parent_action = ranked[0].action_key
    parent = legal.get(parent_action)
    if parent is None:
        raise ValueError("模拟父代首选不在规则合法候选")
    values = screen._route_values(parent)
    if values is None:
        return None, "parent_facts_missing"
    combined, standard, seven, support = values
    options = []
    for item in ranked[1:]:
        action = item.action_key
        if not action.startswith("discard:"):
            continue
        alternate = legal.get(action)
        if alternate is None:
            raise ValueError("模拟评分备选不在规则合法候选")
        values_b = screen._route_values(alternate)
        if values_b is None:
            continue
        c, s, q, u = values_b
        if c != combined or s > standard or q > seven or (s == standard and q == seven) or u < support:
            continue
        options.append((-(standard - s + seven - q), -float(item.score), -u, action,
                        values_b, float(item.score)))
    if not options:
        return None, "no_route_option"
    _gain, _score, _support, alternate_action, values_b, score_b = min(options)
    c, s, q, u = values_b
    hand = screen._hand(raw["observation"])
    kinds = (["standard"] if s < standard else []) + (["seven_pairs"] if q < seven else [])
    return {"game_id": observation.game_id, "table_no": _table_no(observation.game_id),
            "round_no": observation.round_no, "trigger_seq": request.trigger_seq,
            "parent_action": parent_action, "alternate_action": alternate_action,
            "parent_score": float(ranked[0].score), "alternate_score": score_b,
            "parent_route_shanten": [combined, standard, seven],
            "alternate_route_shanten": [c, s, q],
            "parent_support": support, "alternate_support": u,
            "white_count": hand.count("白"),
            "wall_remaining": raw["observation"].get("remaining_tile_count"),
            "route_improvements": kinds, "request_sha256": _digest(raw)}, "eligible"


def _audit(requests: list, source: dict, parent: str) -> dict:
    """逐来源每路线留最早一窗；原始桌分对象不进入输出。"""

    scorer = ActionValueScorer("g10-exposure-audit-" + source["source_id"], parent)
    counts = Counter()
    first_by_kind = {}
    for request in requests:
        counts["focal_requests"] += 1
        row, reason = _eligible(request, scorer)
        counts[reason] += 1
        if row is None:
            continue
        for kind in row["route_improvements"]:
            key = (row["table_no"], row["round_no"], row["trigger_seq"],
                   row["alternate_action"])
            previous = first_by_kind.get(kind)
            if previous is None or key < previous[0]:
                first_by_kind[kind] = (key, row)
    selected = [dict(row, route_kind=kind) for kind, (_key, row) in sorted(first_by_kind.items())]
    return {"counts": dict(sorted(counts.items())), "selected": selected}


def _run_source(source: dict) -> dict:
    contract = json.loads(g1.CONTRACT.read_text(encoding="utf-8"))
    parent = g1.p83.parent_source()
    plans = g1.p83.natural.build_seat_stage_plans(
        contract=contract, opponent=source["mix"], root_index=source["root_index"],
        focal_seat=source["focal_seat"], panel_seed=PANEL_SEED)
    requests = []
    name = "g10-exposure-" + source["source_id"]
    stage = g1.p83.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer(name, parent),
        opponent_policies=contract["panel"]["opponent_scenarios"][source["mix"]]["opponent_policies"],
        versions_block=g1.p83.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=g1.p83.LIMITS, decision_observer=requests.append)
    if stage.get("status") != "complete" or len(stage.get("tables") or []) != TABLES_PER_SOURCE:
        raise RuntimeError(stage.get("error") or "G10 自然桌未完成")
    focal_ids = []
    for plan, table in zip(plans, stage["tables"]):
        seat = plan.seats().index(g1.p83.natural.FOCAL_PARTICIPANT)
        ids = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
        expected = "action_value_v1:" + name
        if len(ids) != 4 or ids[seat] != expected:
            raise RuntimeError("G10 自然桌焦点策略身份漂移")
        focal_ids.append(expected)
    return {"source": source, "status": "complete", "tables": TABLES_PER_SOURCE,
            "focal_policy_ids": focal_ids, "audit": _audit(requests, source, parent)}


def run() -> None:
    """单进程、可续跑，来源桌预算逐项记账。"""

    manifest, frozen = _verify()
    auth = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    g1.p83.natural.require_authorization(auth)
    book = g1.p83.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=g1.p83.search.av_ledger_budgets_from_authorization(auth))
    complete = 0
    for source in frozen:
        path = _path(source)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("已存自然来源不完整")
            complete += TABLES_PER_SOURCE
            continue
        reservation = book.reserve(step_id="g10:exposure:" + source["source_id"],
                                   account="tables_full", amount=TABLES_PER_SOURCE,
                                   note="G10 新根结果盲路线机会")
        try:
            result = _run_source(source)
            _write(path, result)
            book.settle(reservation, actual=TABLES_PER_SOURCE,
                        note="两桌完成且焦点策略身份一致")
            complete += TABLES_PER_SOURCE
        except BaseException:
            book.settle(reservation, usage_unknown=True, note="来源异常，保守计费")
            raise
        if complete % 16 == 0 or complete == manifest["planned_tables"]:
            print(json.dumps({"completed_tables": complete,
                              "planned_tables": manifest["planned_tables"]}), flush=True)
    _write(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "g10-route-option-natural-run/1", "completed_tables": complete,
        "planned_tables": manifest["planned_tables"], "spent": book.account_summary(),
        "outcome_labels_opened": False})


def analyze() -> None:
    """每根每路线按座位、来源桌、局号和序号选最早目标。"""

    manifest, frozen = _verify()
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("G10 自然暴露结果已存在，拒绝覆盖")
    summary_path = _project_file(_PROJECT_ROOT, OUT / "run-summary.json")
    if not summary_path.exists() or json.loads(summary_path.read_text(encoding="utf-8"))["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("G10 自然来源尚未跑满")
    counts = defaultdict(Counter)
    by_root_kind = {}
    for source in frozen:
        document = json.loads(_path(source).read_text(encoding="utf-8"))
        if document["status"] != "complete" or len(document["focal_policy_ids"]) != TABLES_PER_SOURCE:
            raise ValueError("自然来源身份或桌数不完整")
        counts[source["mix"]].update(document["audit"]["counts"])
        for row in document["audit"]["selected"]:
            key = (source["source_root_id"], row["route_kind"])
            order = (source["focal_seat"], row["table_no"], row["round_no"],
                     row["trigger_seq"], row["alternate_action"])
            prior = by_root_kind.get(key)
            if prior is None or order < prior[0]:
                by_root_kind[key] = (order, dict(row, source=source))
    selected = [row for _order, row in by_root_kind.values()]
    selected.sort(key=lambda row: (row["source"]["mix"], row["route_kind"],
                                   row["source"]["root_index"]))
    coverage = {mix: {kind: len({row["source"]["source_root_id"] for row in selected
                                if row["source"]["mix"] == mix and row["route_kind"] == kind})
                      for kind in ("standard", "seven_pairs")} for mix in MIXES}
    result = {"schema": "g10-route-option-natural-exposure/1",
              "parent_source_sha256": manifest["parent_source_sha256"],
              "panel_seed": PANEL_SEED, "planned_tables": manifest["planned_tables"],
              "completed_tables": manifest["planned_tables"],
              "independence_unit": "mix × source_root_id",
              "counts": {mix: dict(sorted(counts[mix].items())) for mix in MIXES},
              "independent_roots_by_route": coverage,
              "teacher_entry_open": {kind: all(coverage[mix][kind] >= 12 for mix in MIXES)
                                     for kind in ("standard", "seven_pairs")},
              "selected": selected, "outcome_labels_opened": False,
              "release_eligible": False}
    _write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"coverage": coverage, "teacher_entry_open": result["teacher_entry_open"],
                      "selected_targets": len(selected)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "analyze": analyze}[args.command]()


if __name__ == "__main__":
    main()
