"""核旧联合候选首分歧当局结算及自然准备取舍；不把整桌差当单动作因果。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter, defaultdict
from pathlib import Path

from common import HERE, OLD, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import background_priority, postprocess_lock


def hand_account(settlement, seat):
    """公开单局结算分账；向量顺序物理0—3，收入/支付单位官方积分。"""
    vector = settlement["score_delta"]
    dev.require(type(vector) is list and len(vector) == 4 and all(type(v) is int for v in vector) and sum(vector) == 0,
        "单局积分向量不是合法四座零和")
    net = vector[seat]
    own = settlement["winner_seat"] == seat
    income = net if own else 0
    large = income if own and settlement["fan"] >= 4 else 0
    payments = net if not own else 0
    dev.require(net == income + payments and income >= 0 and payments <= 0, "本人收入/支付方向矛盾")
    return {"net": net, "own_hu": int(own), "ordinary_income": income - large,
        "large_income": large, "payments": payments, "fan_if_own_hu": settlement["fan"] if own else None,
        "is_dealer": settlement["dealer_seat"] == seat, "is_draw": settlement["is_draw"]}


def main():
    """全128对首分歧当局原件再对账；原后继策略仍不同，所得是配对路径观察。"""
    background_priority()
    with postprocess_lock("prior_closed_first_diverging_hand_account"):
        base = _project_file(_PROJECT_ROOT, HERE / "prior-joint-first-divergences")
        closed, closed_pin = dev.read(base / "CLOSED.json")
        old, old_pin = dev.read(OLD / "DEVELOPMENT-CLOSED.json")
        dev.require(closed["complete"] is True and closed["actual_paired_complete_tables_read"] == 128 and old["complete"] is True,
            "旧配对首分歧未全闭")
        rows_file = base / "rows.jsonl"
        dev.require(pin(rows_file) == closed["rows_file_pin"], "首分歧原行漂移")
        source_rows = [dev.decode(line) for line in rows_file.read_bytes().splitlines()]
        files = {str(p): pin(p) for p in (Path(__file__), rows_file, base / "CLOSED.json", OLD / "DEVELOPMENT-CLOSED.json")}
        tables, groups, preparation, failure = [], defaultdict(Counter), Counter(), None
        try:
            for row in source_rows:
                dev.require(row["status"] == "first_divergence", "首分歧未知，不补造单局")
                selected_round = row["round_no"]
                raw_closures = []
                for path in row["original_decision_files"]:
                    closure_path = Path(path).with_name("CLOSURE.json")
                    actual, actual_pin = dev.read(closure_path)
                    dev.require(old["files"][str(closure_path)] == actual_pin and actual["complete"] is True and
                        len(actual["settlements"]) == len(actual["pairing_proofs"]) == 8, "原完整桌终态漂移")
                    files[str(closure_path)] = actual_pin
                    raw_closures.append(actual)
                proofs = [c["pairing_proofs"][selected_round - 1] for c in raw_closures]
                dev.require(all(p["round_no"] == selected_round for p in proofs) and
                    proofs[0]["physical_wall_sha256"] == proofs[1]["physical_wall_sha256"] and
                    proofs[0]["actual_initial_sha256"] == proofs[1]["actual_initial_sha256"] and
                    proofs[0]["dealer_seat"] == proofs[1]["dealer_seat"], "首分歧单局实际起手、庄位或牌山不同")
                settlements = [c["settlements"][selected_round - 1] for c in raw_closures]
                dev.require(all(s["evidence"] == "public_export_hand_settlement" and s["round_no"] == selected_round for s in settlements),
                    "所选当局不是公开真实结算")
                account = [hand_account(s["settlement"], row["rotation"]) for s in settlements]
                delta = {k: account[1][k] - account[0][k] for k in ("net", "own_hu", "ordinary_income", "large_income", "payments")}
                switch = row["parent_action"].split(":")[0] + "->" + row["child_action"].split(":")[0]
                entry = {"root_id": row["root_id"], "root_index": row["root_index"], "rotation": row["rotation"],
                    "round_no": selected_round, "trigger_seq": row["trigger_seq"], "white_count_at_divergence": row["white_count_at_first_divergence"],
                    "switch": switch, "parent_action": row["parent_action"], "child_action": row["child_action"],
                    "equal_prefix_rows": row["equal_prefix_rows"], "public_view_sha256": row["view_sha256"],
                    "same_initial_and_physical_wall_proof": proofs[0], "parent_hand": account[0], "child_hand": account[1],
                    "first_diverging_hand_delta": delta, "whole_table_net_delta": row["complete_table_delta"]["net"],
                    "remaining_tile_count": row["remaining_tile_count"],
                    "continuation_policies_differ_not_isolated_first_action_effect": True}
                groups[switch]["count"] += 1
                for key, value in delta.items():
                    groups[switch][key + "_first_hand_delta"] += value
                groups[switch]["whole_table_net_delta"] += entry["whole_table_net_delta"]
                if switch == "discard->discard":
                    # 两弃牌根是直接等待态：只核自然目标的同缺张/同弃张宽度，不冒称实际向听或整体支配。
                    facts = [c["trace"]["detail"]["prep"][:3] for c in row["parent_scores"]]
                    newfacts = [c["trace"]["detail"]["prep"][:3] for c in row["child_scores"]]
                    dev.require(facts == newfacts and all(type(v) is int for f in facts for v in f), "两实现同弃牌根自然数学事实不一致")
                    same_burden = facts[0][:2] == facts[1][:2]
                    direction = "burden_changed"
                    if same_burden:
                        direction = "wider" if facts[1][2] > facts[0][2] else "narrower" if facts[1][2] < facts[0][2] else "same_width"
                    entry["natural_preparation_only"] = {"parent_choice_need_discard_width": facts[0],
                        "child_choice_need_discard_width": facts[1], "same_need_and_discard": same_burden,
                        "child_width_direction": direction, "not_total_efficiency_dominance": True}
                    preparation[direction] += 1
                tables.append(entry)
            dev.require(len(tables) == 128 and sum(t["whole_table_net_delta"] for t in tables) == closed["net_delta_sum_all_128_complete_tables"],
                "全部配对桌账目不一致")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "completed_pairs": len(tables)}
        stable = all(pin(Path(p)) == expected for p, expected in files.items())
        complete = failure is None and len(tables) == 128 and stable
        save(_project_file(_PROJECT_ROOT, HERE / "PRIOR-JOINT-DIVERGING-HANDS.json"), {"complete": complete, "failure": failure, "source_stable": stable,
            "files": files, "old_closed_pin": old_pin, "first_divergence_closed_pin": closed_pin,
            "same_first_diverging_hand_initial_and_wall_verified_pairs": len(tables), "groups": dict(groups),
            "natural_preparation_directions_for_102_discard_switches": dict(preparation), "rows": tables,
            "new_scores_worlds_tables_model_calls_HTTP": 0, "current_development_data_read": False,
            "post_selected_path_diagnosis_not_independent_strength_or_single_action_causal_evidence": True})
        dev.require(complete, "首分歧当局对账未通过，原错误保留")
        print({"complete": complete, "groups": dict(groups), "natural_preparation_directions": dict(preparation)}, flush=True)


if __name__ == "__main__":
    main()
