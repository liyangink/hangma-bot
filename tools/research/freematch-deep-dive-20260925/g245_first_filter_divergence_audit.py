#!/usr/bin/env python3
"""G245：只读复核 G243/G239 同墙阶段的首次过滤分歧。"""

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


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g245-first-filter-divergence-20260929/result.json')
G243 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g243-competing-risk-filter-development-20260929')
G244 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g244-same-wall-filter-attribution-20260929')
G242 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g242-competing-risk-calibration-20260929/result.json')
METRIC_KEYS = (
    "decision_id", "parent_action", "candidate_action", "parent_standard_shanten",
    "candidate_standard_shanten", "parent_seven_pairs_shanten",
    "candidate_seven_pairs_shanten", "parent_baotou_after",
    "candidate_baotou_after", "parent_standard_width",
    "candidate_standard_width", "score_gap", "eligible_numeric_alternatives",
)


def digest(path: Path) -> str:
    """对已保存的阶段原文计算摘要，避免只凭文件名对账。"""
    return sha256(path.read_bytes()).hexdigest()


def metric_identity(row: dict) -> tuple:
    """比较两策略共享的行动前规则事实，排除状态和耗时字段。"""
    return tuple(row[key] if not isinstance(row[key], list) else tuple(row[key])
                 for key in METRIC_KEYS)


def location(decision_id: str) -> tuple[str, int]:
    """由本地决策标识提取完整桌和官方事件所处单局。"""
    parts = decision_id.split(":")
    if len(parts) != 8 or parts[0] != "sitin-stage" or parts[2] != "sitin-stage":
        raise ValueError("G245 非预期决策标识")
    if parts[1] != parts[3] or not parts[4].isdigit():
        raise ValueError("G245 决策标识内桌号／单局号不一致")
    return parts[1], int(parts[4])


def by_table(metrics: list[dict], table_ids: list[str]) -> dict[str, list[dict]]:
    """保持原始执行顺序，禁止把分歧后的相同事件号误当同一观察。"""
    grouped: dict[str, list[dict]] = {table_id: [] for table_id in table_ids}
    for row in metrics:
        table_id, _ = location(row["decision_id"])
        if table_id not in grouped:
            raise ValueError("G245 指标指向阶段外完整桌")
        grouped[table_id].append(row)
    return grouped


def terminal_numeric(key: str) -> bool:
    """弃一／九数牌这一可见动作类别，与 G242 特征定义一致。"""
    code = key.split(":", 1)[1]
    return len(code) == 2 and code[0] in "19" and code[1] in "wbt"


def first_row(mix: str, root: int, seat: int, x: dict, y: dict) -> dict | None:
    """验证首次过滤前两臂事实完全一致，再读取后续结算。"""
    xtables, ytables = x["stage"]["tables"], y["stage"]["tables"]
    ids = [table["table_id"] for table in xtables]
    if ids != [table["table_id"] for table in ytables] or len(ids) != 2:
        raise ValueError("G245 两臂完整桌身份不一致")
    if [table["seed"] for table in xtables] != [table["seed"] for table in ytables]:
        raise ValueError("G245 牌山种子不一致")
    for table in (*xtables, *ytables):
        if table["hand_account"]["complete_hands"] != 8:
            raise ValueError("G245 八局完整性失败")
    xm = by_table(x["stage"]["g243_metrics"], ids)
    ym = by_table(y["stage"]["g244_metrics"], ids)
    for index, table_id in enumerate(ids):
        filtered = next(((offset, row) for offset, row in enumerate(xm[table_id])
                         if row["status"] == "filtered"), None)
        if filtered is None:
            if [metric_identity(row) for row in xm[table_id]] != [
                    metric_identity(row) for row in ym[table_id]]:
                raise ValueError("G245 无过滤桌的提案序列不一致")
            if any(row["status"] != "adopted" for row in xm[table_id] + ym[table_id]):
                raise ValueError("G245 无过滤桌出现非采用状态")
            if xtables[index]["hand_records"] != ytables[index]["hand_records"]:
                raise ValueError("G245 无过滤桌结算不一致")
            continue
        offset, metric = filtered
        if offset >= len(ym[table_id]) or [
                metric_identity(row) for row in xm[table_id][:offset + 1]] != [
                    metric_identity(row) for row in ym[table_id][:offset + 1]]:
            raise ValueError("G245 首分歧前同一观察／规则事实未对齐")
        if (any(row["status"] != "adopted" for row in xm[table_id][:offset])
                or any(row["status"] != "adopted" for row in ym[table_id][:offset + 1])):
            raise ValueError("G245 首分歧前策略动作状态不一致")
        actual_id, round_no = location(metric["decision_id"])
        if actual_id != table_id:
            raise ValueError("G245 首分歧桌身份不一致")
        focal_seat_in_table = xtables[index]["hand_account"]["focal_seat"]
        if (focal_seat_in_table != ytables[index]["hand_account"]["focal_seat"]
                or metric["decision_id"].split(":")[-1]
                != f"seat{focal_seat_in_table}"):
            raise ValueError("G245 当前完整桌本座换位或决策座位不一致")
        xhand = next(row for row in xtables[index]["hand_records"]
                     if row["round_no"] == round_no)
        yhand = next(row for row in ytables[index]["hand_records"]
                     if row["round_no"] == round_no)
        if ([row for row in xtables[index]["hand_records"] if row["round_no"] < round_no]
                != [row for row in ytables[index]["hand_records"]
                    if row["round_no"] < round_no]
                or xhand["scores_before"] != yhand["scores_before"]):
            raise ValueError("G245 首分歧前局分／历史单局不一致")
        if metric["parent_standard_shanten"] != metric["candidate_standard_shanten"]:
            raise ValueError("G245 首分歧普通型向听不相等")
        width_types = (metric["candidate_standard_width"][0]
                       - metric["parent_standard_width"][0])
        width_capacity = (metric["candidate_standard_width"][1]
                          - metric["parent_standard_width"][1])
        if width_types <= 0 or width_capacity <= 0:
            raise ValueError("G245 首分歧并非严格宽面备选")
        table_delta = (ytables[index]["hand_account"]["focal_table_delta"]
                       - xtables[index]["hand_account"]["focal_table_delta"])
        stage_delta = y["stage"]["focal_stage_score"] - x["stage"]["focal_stage_score"]
        account_delta = sum(
            yt["hand_account"]["focal_table_delta"]
            - xt["hand_account"]["focal_table_delta"]
            for xt, yt in zip(xtables, ytables))
        if stage_delta != account_delta:
            raise ValueError("G245 阶段净分与完整桌分量不一致")
        return {
            "mix": mix, "root_index": root, "focal_seat": seat,
            "focal_seat_in_table": focal_seat_in_table,
            "table_index": index + 1, "table_id": table_id,
            "round_no": round_no, "decision_id": metric["decision_id"],
            "parent_action": metric["parent_action"],
            "wider_action": metric["candidate_action"],
            "width_type_gain": width_types,
            "width_public_capacity_gain": width_capacity,
            "parent_standard_shanten": metric["parent_standard_shanten"],
            "parent_seven_pairs_shanten": metric["parent_seven_pairs_shanten"],
            "wider_seven_pairs_shanten": metric["candidate_seven_pairs_shanten"],
            "baotou_state_equal": metric["parent_baotou_after"]
                                    == metric["candidate_baotou_after"],
            "wider_discards_terminal": terminal_numeric(metric["candidate_action"]),
            "parent_discards_terminal": terminal_numeric(metric["parent_action"]),
            "predicted_ownwin_gain": metric["predicted_ownwin_gain"],
            "parent_score_advantage": metric["score_gap"],
            "target_hand_delta_g239_minus_g243":
                yhand["score_delta"][focal_seat_in_table]
                - xhand["score_delta"][focal_seat_in_table],
            "first_divergence_table_delta_g239_minus_g243": table_delta,
            "full_stage_delta_g239_minus_g243": stage_delta,
            "target_hand_outcomes": {
                arm: {"winner_seat": hand["winner_seat"], "fan": hand["fan"],
                      "details": hand["details"], "focal_score_delta":
                      hand["score_delta"][focal_seat_in_table]}
                for arm, hand in (("g243_filtered", xhand), ("g239_wider", yhand))},
        }
    if x["stage"]["focal_stage_score"] != y["stage"]["focal_stage_score"]:
        raise ValueError("G245 全阶段无过滤但净分不同")
    return None


def summarize(rows: list[dict], no_filter: list[str], g244_result: dict) -> dict:
    """只按独立阶段与完整桌聚合描述，不把 55 次首分歧当独立根。"""
    model = json.loads(G242.read_text(encoding="utf-8"))
    names = model["full_feature_order"]
    coeff = dict(zip(names, model["full_coefficients"]))
    own_third = {name: value[1] - value[0] for name, value in coeff.items()}
    groups = defaultdict(list)
    contributions = Counter()
    for row in rows:
        groups[row["mix"]].append(row)
        seven = (row["wider_seven_pairs_shanten"]
                 - row["parent_seven_pairs_shanten"]
                 if row["parent_seven_pairs_shanten"] is not None else 0)
        contributions["width_types"] += (row["width_type_gain"] / 12.0
                                         * own_third["standard_useful_type_count"])
        contributions["width_public_capacity"] += (
            row["width_public_capacity_gain"] / 48.0
            * own_third["standard_useful_public_capacity"])
        contributions["seven_pairs_shanten"] += (
            seven / 6.0 * own_third["seven_pairs_shanten_clipped"])
        contributions["discard_terminal_numeric"] += (
            (int(row["wider_discards_terminal"])
             - int(row["parent_discards_terminal"]))
            * own_third["discard_terminal_numeric"])
    by_mix = {}
    rotated = [row for row in rows if row["table_index"] == 2]
    if any(row["focal_seat_in_table"] == row["focal_seat"] for row in rotated):
        raise ValueError("G245 第二张完整桌未按预期换座")
    for mix in ("H", "M"):
        group = groups[mix]
        stage_deltas = [row["full_stage_delta_g239_minus_g243"] for row in group]
        by_mix[mix] = {
            "first_divergence_stages": len(group),
            "first_in_table_1": sum(row["table_index"] == 1 for row in group),
            "first_in_table_2": sum(row["table_index"] == 2 for row in group),
            "wider_discards_terminal": sum(row["wider_discards_terminal"]
                                            for row in group),
            "stage_delta_sum": sum(stage_deltas),
            "stage_delta_positive_equal_negative": [
                sum(value > 0 for value in stage_deltas),
                sum(value == 0 for value in stage_deltas),
                sum(value < 0 for value in stage_deltas)],
            "target_hand_delta_sum": sum(
                row["target_hand_delta_g239_minus_g243"] for row in group),
        }
        expected = (g244_result["mean_delta_per_complete_table"]["g243_minus_g239"][mix]
                    * -128)
        if abs(by_mix[mix]["stage_delta_sum"] - expected) > 1e-9:
            raise ValueError("G245 首分歧阶段差与 G244 冻结净分不守恒")
    terminal_groups = {}
    for flag in (False, True):
        subset = [row for row in rows if row["wider_discards_terminal"] == flag]
        terminal_groups[str(flag).lower()] = {
            "stages": len(subset),
            "stage_delta_sum": sum(row["full_stage_delta_g239_minus_g243"]
                                   for row in subset),
            "stage_delta_positive_equal_negative": [
                sum(row["full_stage_delta_g239_minus_g243"] > 0 for row in subset),
                sum(row["full_stage_delta_g239_minus_g243"] == 0 for row in subset),
                sum(row["full_stage_delta_g239_minus_g243"] < 0 for row in subset)],
        }
    terminal_feature_groups = {}
    for change in (0, 1):
        subset = [row for row in rows if (
            int(row["wider_discards_terminal"])
            - int(row["parent_discards_terminal"])) == change]
        terminal_feature_groups[str(change)] = {
            "stages": len(subset),
            "stage_delta_sum": sum(row["full_stage_delta_g239_minus_g243"]
                                   for row in subset),
            "stage_delta_positive_equal_negative": [
                sum(row["full_stage_delta_g239_minus_g243"] > 0 for row in subset),
                sum(row["full_stage_delta_g239_minus_g243"] == 0 for row in subset),
                sum(row["full_stage_delta_g239_minus_g243"] < 0 for row in subset)],
        }
    return {
        "paired_stages": 128, "no_filter_identical_stages": len(no_filter),
        "first_filter_divergence_stages": len(rows),
        "first_filter_in_rotated_table": len(rotated),
        "width_type_gain_distribution": dict(sorted(Counter(
            row["width_type_gain"] for row in rows).items())),
        "width_public_capacity_gain_range": [
            min(row["width_public_capacity_gain"] for row in rows),
            max(row["width_public_capacity_gain"] for row in rows)],
        "seven_pairs_shanten_better_equal_worse": [
            sum(row["wider_seven_pairs_shanten"] is not None
                and row["parent_seven_pairs_shanten"] is not None
                and row["wider_seven_pairs_shanten"] < row["parent_seven_pairs_shanten"]
                for row in rows),
            sum(row["wider_seven_pairs_shanten"] == row["parent_seven_pairs_shanten"]
                for row in rows),
            sum(row["wider_seven_pairs_shanten"] is not None
                and row["parent_seven_pairs_shanten"] is not None
                and row["wider_seven_pairs_shanten"] > row["parent_seven_pairs_shanten"]
                for row in rows)],
        "baotou_state_equal": sum(row["baotou_state_equal"] for row in rows),
        "by_mix": by_mix, "by_wider_discard_terminal": terminal_groups,
        "by_terminal_feature_change": terminal_feature_groups,
        "filtered_predicted_ownwin_gain_range": [
            min(row["predicted_ownwin_gain"] for row in rows),
            max(row["predicted_ownwin_gain"] for row in rows)],
        "g242_mean_ownwin_vs_third_logit_contribution": {
            key: value / len(rows) for key, value in sorted(contributions.items())},
        "g242_discard_terminal_ownwin_vs_third_coefficient":
            own_third["discard_terminal_numeric"],
        "g242_capacity_ownwin_vs_third_coefficient":
            own_third["standard_useful_public_capacity"],
    }


def main() -> None:
    """核每份原始阶段摘要、首分歧对齐和冻结 G244 分账后写结果。"""
    manifest = json.loads((_project_file(_PROJECT_ROOT, G244 / "manifest.json")).read_text(encoding="utf-8"))
    g244_result = json.loads((_project_file(_PROJECT_ROOT, G244 / "result.json")).read_text(encoding="utf-8"))
    if len(manifest["g243_stage_sha256"]) != 256:
        raise ValueError("G245 G243 来源摘要未冻结")
    rows, no_filter = [], []
    hashes = {}
    for mix in ("H", "M"):
        for root in range(1, 17):
            for seat in range(4):
                stem = f"{mix}-r{root:04d}-s{seat}"
                x_path = _project_file(_PROJECT_ROOT, G243 / "stages" / f"{stem}-g243_competing_risk_filter.json")
                y_path = _project_file(_PROJECT_ROOT, G244 / "stages" / f"{stem}-g239_numeric_route.json")
                if digest(x_path) != manifest["g243_stage_sha256"][x_path.name]:
                    raise ValueError("G245 G243 已冻结来源被改动")
                hashes[x_path.name] = digest(x_path)
                hashes[y_path.name] = digest(y_path)
                x = json.loads(x_path.read_text(encoding="utf-8"))
                y = json.loads(y_path.read_text(encoding="utf-8"))
                if any(arm["mix"] != mix or arm["root_index"] != root
                       or arm["focal_seat"] != seat for arm in (x, y)):
                    raise ValueError("G245 阶段身份不一致")
                row = first_row(mix, root, seat, x, y)
                if row is None:
                    no_filter.append(stem)
                else:
                    rows.append(row)
    result = {
        "schema": "g245-first-filter-divergence-audit/2",
        "analysis_script_sha256": digest(Path(__file__)),
        "g242_model_sha256": digest(G242),
        "g244_result_sha256": digest(_project_file(_PROJECT_ROOT, G244 / "result.json")),
        "source_stage_sha256": dict(sorted(hashes.items())),
        "summary": summarize(rows, no_filter, g244_result),
        "no_filter_identical_stage_ids": no_filter,
        "first_divergence_rows": rows,
        "correction": "v1 用阶段起始座位索引第二张换位桌的目标单局分；v2 从各桌 hand_account.focal_seat 读取并与决策座位对账。完整阶段净分、首次分歧和模型贡献未变。",
        "boundary": "已看 G243/G244 同墙牌山的事后首分歧归因；完整阶段净分是两策略续打差，不是单次弃牌因果效应或新候选收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                   + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
