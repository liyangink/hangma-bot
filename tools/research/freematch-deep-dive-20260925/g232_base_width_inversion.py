#!/usr/bin/env python3
"""G232：在未按赢家筛选的父代窗口重判宽进张基础分反转。"""

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

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g224_g223_vector_replay as g224
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G232-BASE-WIDTH-INVERSION-PREREG-2026-09-29.md')
SOURCE = g224.OUT / "result.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g232-base-width-inversion-20260929/result.json')


def digest(path: Path) -> str:
    """绑定行动前来源、判据与执行代码。"""

    return sha256(path.read_bytes()).hexdigest()


def width(tiles) -> tuple[int, int] | None:
    """返回正公开容量的牌码种数和可见物理上界张数。"""

    if tiles is None:
        return None
    values = [item.remaining_estimate for item in tiles]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return sum(value > 0 for value in values), sum(values)


def vector(tiles) -> tuple[tuple[str, int], ...]:
    """保留生产规则的逐码容量，以对账 G224 冻结补证。"""

    if tiles is None:
        raise ValueError("普通逐码有效牌事实缺失")
    return tuple(sorted((item.code, item.remaining_estimate) for item in tiles))


def trace_parts(entry: dict) -> dict[str, float]:
    """逐分量守恒，未知覆盖项留在 other，不强行归给熟牌。"""

    trace = entry["trace"]
    names = ("base_score", "wealth_part", "wealth_discard_part",
             "river_part", "style_part")
    values = {}
    for name in names:
        value = trace.get(name)
        if type(value) not in (int, float):
            raise ValueError("R18 评分分量缺失：" + name)
        values[name] = float(value)
    risk = trace.get("risk_units")
    if type(risk) not in (int, float) or risk < 0:
        raise ValueError("R18 风险单位缺失")
    values["risk_units"] = float(risk)
    values["risk_part"] = -6.0 * float(risk)
    values["other"] = float(entry["score"]) - sum(
        values[name] for name in names) - values["risk_part"]
    if abs(sum(values[name] for name in names) + values["risk_part"]
           + values["other"] - float(entry["score"])) > 1e-8:
        raise ValueError("评分分量不守恒")
    return values


def inspect_root(raw: dict, *, mix: str, root_index: int, start_seat: int,
                 scorer) -> dict:
    """仅按当前可见观察选代表宽面备选，绝不读取后续成绩。"""

    observation = observation_from_json(raw["observation"])
    request = g87.request_for(observation)
    if not raw["root_decision_id"]:
        raise ValueError("根观察缺动作身份")
    legal = {item.action_key: item.facts for item in request.rules.legal_candidates}
    view = build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
    scored = scorer(view)
    if scored.get("status") != "SCORED":
        raise ValueError("冻结 R18 未完整评分")
    entries = {item["action_key"]: item for item in scored["entries"]}
    if len(entries) != len(scored["entries"]):
        raise ValueError("评分动作键重复")
    parent_key = raw["root_action"]
    if parent_key not in legal or parent_key not in entries:
        raise ValueError("G224 父代动作缺失")
    scores = {key: float(item["score"]) for key, item in entries.items()}
    if g87.argmax(scores) != parent_key:
        raise ValueError("父代首选与 G224 轨迹不符")
    parent = next(item for item in raw["same_layer_options"]
                  if item["action"] == parent_key)
    parent_fact = legal[parent_key]
    if (parent_fact is None
            or width(parent_fact.standard_useful_tiles) != tuple(parent["standard_width"])
            or vector(parent_fact.standard_useful_tiles) != tuple(sorted(
                (item["code"], item["public_capacity"])
                for item in parent["standard_useful_tiles"]))):
        raise ValueError("G224 父代普通进张事实漂移")
    parent_width = width(parent_fact.standard_useful_tiles)
    parent_combined = width(parent_fact.useful_tiles)
    parent_parts = trace_parts(entries[parent_key])
    strict, guarded, inversions = [], [], []
    for option in raw["same_layer_options"]:
        key = option["action"]
        if key not in entries or key not in legal:
            raise ValueError("G224 同层备选不在重建评分或合法集合")
        facts = legal[key]
        if (facts is None
                or width(facts.standard_useful_tiles) != tuple(option["standard_width"])
                or vector(facts.standard_useful_tiles) != tuple(sorted(
                    (item["code"], item["public_capacity"])
                    for item in option["standard_useful_tiles"]))
                or abs(scores[parent_key] - scores[key]
                       - option["parent_score_gap"]) > 1e-8):
            raise ValueError("G224 备选向听、逐码容量或评分差漂移")
        if (key == parent_key or not parent_key.startswith("discard:")
                or parent_key == "discard:白" or not key.startswith("discard:")
                or key == "discard:白"):
            continue
        candidate_width = width(facts.standard_useful_tiles)
        if (candidate_width is None or parent_width is None
                or candidate_width[0] <= parent_width[0]
                or candidate_width[1] <= parent_width[1]):
            continue
        strict.append(key)
        candidate_parts = trace_parts(entries[key])
        candidate_combined = width(facts.useful_tiles)
        protected = (
            type(facts.shanten_after) is int
            and type(parent_fact.shanten_after) is int
            and facts.shanten_after <= parent_fact.shanten_after
            and candidate_combined is not None and parent_combined is not None
            and candidate_combined[1] >= parent_combined[1]
            and type(facts.seven_pairs_shanten_after) is int
            and type(parent_fact.seven_pairs_shanten_after) is int
            and facts.seven_pairs_shanten_after <= parent_fact.seven_pairs_shanten_after
            and candidate_parts["risk_units"] <= parent_parts["risk_units"] + 1e-8
            and (parent_fact.baotou_after is not True
                 or facts.baotou_after is True)
        )
        if not protected:
            continue
        guarded.append(key)
        delta = {name: candidate_parts[name] - parent_parts[name]
                 for name in ("base_score", "wealth_part", "wealth_discard_part",
                              "river_part", "style_part", "risk_part", "other")}
        total = scores[key] - scores[parent_key]
        if abs(sum(delta.values()) - total) > 1e-8:
            raise ValueError("两动作评分差不守恒")
        no_river_style = total - delta["river_part"] - delta["style_part"]
        if not (delta["base_score"] > 1e-8 and total <= 1e-8
                and no_river_style > 1e-8):
            continue
        white = raw["root_shape"]["white_after"]
        g193_eligible = (
            facts.standard_shanten_after == 3 and white <= 1
            and not observation.melds[observation.seat]
            and not observation.rule_state.baotou
            and not observation.rule_state.chain_count
            and candidate_width[1] >= parent_width[1] + 3
            and -1e-8 <= -total <= 4.0 + 1e-8
        )
        inversions.append({
            "action": key, "standard_width": list(candidate_width),
            "width_gain": [candidate_width[0] - parent_width[0],
                           candidate_width[1] - parent_width[1]],
            "score_gap": round(-total, 8),
            "score_parts_delta": {name: round(value, 8)
                                  for name, value in delta.items()},
            "score_without_river_style_delta": round(no_river_style, 8),
            "g193_guard_eligible_upper_bound": g193_eligible,
        })
    chosen = min(inversions, key=lambda item: (
        -item["standard_width"][0], -item["standard_width"][1],
        item["score_gap"], item["action"])) if inversions else None
    return {
        "mix": mix, "root_index": root_index, "start_seat": start_seat,
        "table_id": raw["table_id"], "round_no": raw["round_no"],
        "snapshot_seq": observation.snapshot_seq,
        "seat": observation.seat, "white_after": raw["root_shape"]["white_after"],
        "standard_shanten_after": raw["root_shape"]["standard_shanten_after"],
        "parent_action": parent_key, "parent_width": list(parent_width),
        "strict_wider_count": len(strict), "guarded_wider_count": len(guarded),
        "base_width_inversions": len(inversions),
        "representative_inversion": chosen,
    }


def summary(rows: list[dict]) -> dict:
    """按窗口和每桌首次命中双口径报告，独立根单列。"""

    groups = defaultdict(list)
    for row in rows:
        bucket = min(row["white_after"], 2)
        groups[(row["mix"], bucket, row["standard_shanten_after"])].append(row)
    out = {}
    for key, items in sorted(groups.items()):
        matched = [item for item in items if item["representative_inversion"]]
        first_by_table = {}
        for item in sorted(matched, key=lambda row: (
                row["table_id"], row["round_no"], row["snapshot_seq"])):
            first_by_table.setdefault(item["table_id"], item)
        out[f"{key[0]}-white{key[1]}-standard{key[2]}"] = {
            "root_windows": len(items),
            "strict_wider_windows": sum(item["strict_wider_count"] > 0 for item in items),
            "guarded_wider_windows": sum(item["guarded_wider_count"] > 0 for item in items),
            "base_width_inversion_windows": len(matched),
            "base_width_inversion_tables": len(first_by_table),
            "base_width_inversion_independent_roots": len({
                (item["mix"], item["root_index"]) for item in matched}),
            "g193_guard_eligible_upper_bound_windows": sum(
                item["representative_inversion"]["g193_guard_eligible_upper_bound"]
                for item in matched),
        }
    return out


def main() -> None:
    """全部来源重建成功后才保存机读普查。"""

    if OUT.exists():
        raise FileExistsError("G232 结果已存在，拒绝覆盖")
    prior = json.loads(SOURCE.read_text(encoding="utf-8"))
    if (prior.get("schema") != "g224-g223-vector-replay-result/1"
            or prior.get("probe_windows") != 2191
            or prior.get("complete_tables_verified") != 128
            or len(prior.get("stage_sha256", {})) != 64):
        raise ValueError("G224 冻结父代来源规模漂移")
    scorer = c31.load_parent()
    rows = []
    for mix in g224.g223.MIXES:
        for root in g224.g223.ROOTS:
            for seat in g224.g223.SEATS:
                path = g224.stage_path(mix, root, seat)
                if digest(path) != prior["stage_sha256"].get(path.name):
                    raise ValueError("G224 阶段 SHA-256 不符：" + path.name)
                stage = json.loads(path.read_text(encoding="utf-8"))
                if ((stage["mix"], stage["root_index"], stage["start_seat"])
                        != (mix, root, seat)):
                    raise ValueError("阶段身份不符")
                for raw in stage["roots"]:
                    rows.append(inspect_root(raw, mix=mix, root_index=root,
                                             start_seat=seat, scorer=scorer))
    if len(rows) != 2191:
        raise ValueError("G224 根窗口不守恒")
    counts = Counter()
    for row in rows:
        counts["strict_wider_windows"] += row["strict_wider_count"] > 0
        counts["guarded_wider_windows"] += row["guarded_wider_count"] > 0
        counts["base_width_inversion_windows"] += bool(row["representative_inversion"])
        if row["representative_inversion"]:
            counts["g193_guard_eligible_upper_bound_windows"] += row[
                "representative_inversion"]["g193_guard_eligible_upper_bound"]
    payload = {
        "schema": "g232-base-width-inversion/1",
        "source_sha256": {"prereg": digest(PLAN), "script": digest(Path(__file__)),
                          "g224_result": digest(SOURCE),
                          "r18_policy": digest(_project_file(_PROJECT_ROOT, HERE.parents[1] /
                                               "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "source_tables": 128, "root_windows": len(rows),
        "counts": dict(counts), "by_stratum": summary(rows), "rows": rows,
        "boundary": "行动前评分反转普查；G193 标记仅为判据上界，非实际触发、收益或发布证据。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"root_windows": len(rows), "counts": dict(counts)},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
