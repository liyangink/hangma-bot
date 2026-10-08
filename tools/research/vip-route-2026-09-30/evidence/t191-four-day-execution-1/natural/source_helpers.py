"""复用已核完整桌原件校验与积分账本，仅更换批次路径/来源范围/游戏前缀。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/natural'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from t185_close_development import *

def preflight(plan, plan_pin):
    """先核全部原桌终态及身份，尚不提取积分；任何缺桌/失败使整批未知。"""
    tables, arms, initial_hashes, wall_hashes, opponent_vectors = [], [plan["parent"], *plan["candidates"]], {}, {}, {}
    for index in plan["root_indices"]:
        root = plan["roots"][index - 1]
        for rotation in plan["rotations"]:
            for arm_index, arm in enumerate(arms):
                directory = Path(plan["output_directory"]) / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}"
                start, start_pin = read(directory / "START.json")
                closure, closure_pin = read(directory / "CLOSURE.json")
                pairing, pairing_pin = read(directory / "PAIRING-IDENTITY.json")
                label = f"原桌{index}/{rotation}/{arm_index}"
                require(start.get("plan_pin") == plan_pin, label + "未绑定原计划")
                for record in (start, closure):
                    require(record.get("root") == root and record.get("rotation") == rotation and
                            record.get("arm") == arm, label + "来源/座位/公式身份不符")
                    require(record.get("model_calls") == 0, label + "意外模型费用")
                require(start.get("table_starts_reserved") == 1 and
                        start.get("logical_clock_not_official_deadline") is True, label + "启动声明不符")
                require(closure.get("complete") is True and closure.get("failure") is None and
                        closure.get("source_stable") is True, label + "未完成或原运行失败/漂移")
                require(closure.get("normal_fallbacks_allowed") is False and
                        closure.get("deadline_or_strength_admission") is False and
                        closure.get("focal_seat") == rotation, label + "回退/准入/焦点字段不符")
                require(closure.get("actual_table_starts") == 1, label + "启动次数不符")
                require(pairing_pin == closure.get("pairing_identity_pin"), label + "实际配对映射原件未绑定")
                require(pairing.get("root") == root and pairing.get("rotation") == rotation and
                        pairing.get("arm") == arm and pairing.get("evidence") ==
                        "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None",
                        label + "实际配对映射来源不符")
                opponents = pairing.get("opponent_policy_ids_physical")
                require(type(opponents) is list and len(opponents) == 4 and opponents[rotation] is None and
                        all(type(opponents[s]) is str and opponents[s] for s in range(4) if s != rotation) and
                        opponents == closure.get("opponent_policy_ids_physical"), label + "实际对手四席身份不完整")
                require(opponent_vectors.setdefault((index, rotation), opponents) == opponents,
                        label + "父子实际对手映射不同")
                proofs = closure.get("pairing_proofs")
                require(type(proofs) is list and len(proofs) == 8, label + "同牌山证明不足八单局")
                for round_no, proof in enumerate(proofs, 1):
                    require(type(proof.get("round_no")) is int and proof["round_no"] == round_no and type(proof.get("dealer_seat")) is int and
                            0 <= proof["dealer_seat"] < 4 and proof.get("export_matches_frozen_sampler") is True and
                            proof.get("teacher_only_not_policy_input") is True, label + "公开导出/冻结采样器证明无效")
                    wall_hash = sha256(proof.get("physical_wall_sha256"), "实际物理牌山")
                    initial_hash = sha256(proof.get("actual_initial_sha256"), "实际单局起手")
                    wall_key = (index, round_no)
                    require(wall_hashes.setdefault(wall_key, wall_hash) == wall_hash, label + "同源同单局物理牌山不相同")
                    if round_no == 1:
                        require(proof["dealer_seat"] == 0 and initial_hashes.setdefault(index, initial_hash) == initial_hash,
                                label + "所有臂/换座的实际初庄或首局起手不相同")
                outcome, capture = closure.get("outcome"), closure.get("capture")
                require(type(outcome) is dict and outcome.get("status") == "complete" and
                        outcome.get("completed_hands") == 8 and outcome.get("blocked_reason") is None and
                        outcome.get("error_reason") is None, label + "不是完整八单局")
                counts = outcome.get("runtime_counts")
                require(type(counts) is dict and set(counts) == RUNTIME_KEYS and
                        all(type(v) is int and v == 0 for v in counts.values()), label + "故障计数未知或非零")
                require(type(closure.get("settlements")) is list and len(closure["settlements"]) == 8,
                        label + "结算分母不足")
                require(type(capture) is dict and type(capture.get("terminal")) is dict and
                        all(capture["terminal"].get(k) is True for k in
                            ("terminal_valid", "closed", "verified", "store_calls_reconciled")) and
                        capture["terminal"].get("errors") == [], label + "输入捕获终态无效")
                integer(closure.get("actual_focal_decisions"), label + "焦点决策数", 1)
                integer(closure.get("actual_focal_score_calls"), label + "实际评分数", 1)
                require((directory / "views.jsonl.gz").is_file() and
                        (directory / "focal-decisions.jsonl.gz").is_file(), label + "缺评分原件")
                tables.append(TableEvidence(index, rotation, arm_index, directory, start_pin, closure_pin, pairing_pin))
    require(len(tables) == plan["planned_table_instances"], "全批原桌分母不符")
    return tables

def account(settlements, seat, root_id):
    """八份生产公开结算分账；高番累计阈值不是互斥收入，庄闲按每局实际庄家。"""
    overall = dict.fromkeys(ACCOUNT_KEYS, 0)
    dealer, non_dealer = overall.copy(), overall.copy()
    before = [0, 0, 0, 0]
    for round_no, exported in enumerate(settlements, 1):
        require(exported.get("evidence") == "public_export_hand_settlement" and
                exported.get("root_id") == root_id and exported.get("match_id") == "t191-development:" + root_id and
                exported.get("initial_dealer_physical") == 0 and exported.get("round_no") == round_no and
                exported.get("observation_scope") == "completed_hand_only", "结算导出身份或顺序不符")
        s = exported["settlement"]
        require(s.get("coverage") == "settlement_only" and s.get("round_no") == round_no, "结算公开结构不符")
        start, end, delta = (seat_vector(s.get(k), k) for k in ("scores_before", "scores_after", "score_delta"))
        require(start == before and sum(delta) == 0 and
                all(start[i] + delta[i] == end[i] for i in range(4)), "单局积分不守恒或前后不连续")
        dealer_seat = integer(s.get("dealer_seat"), "实际庄家", 0)
        require(dealer_seat < 4 and (round_no != 1 or dealer_seat == 0), "实际初庄或庄家座位不符")
        one = dict.fromkeys(ACCOUNT_KEYS, 0)
        one.update(net=delta[seat], hands=1)
        require(type(s.get("is_draw")) is bool, "流局状态未知")
        if s["is_draw"]:
            require(delta == [0, 0, 0, 0] and s.get("winner_seat") is None, "流局结算矛盾")
            one["draws"] = 1
        else:
            winner, fan = integer(s.get("winner_seat"), "赢家", 0), integer(s.get("fan"), "实际番数", 1)
            require(winner < 4 and delta[winner] > 0 and
                    all(delta[i] <= 0 for i in range(4) if i != winner), "赢家/支付方向不符")
            if winner == seat:
                ordinary = fan < 4
                one["own_hu"] = 1
                one["ordinary_hu" if ordinary else "large_hu"] = 1
                one["ordinary_hu_income" if ordinary else "large_hu_income"] = delta[seat]
                for threshold in (8, 16, 32):
                    if fan >= threshold:
                        one[f"own_hu_ge{threshold}"] = 1
                        one[f"own_hu_ge{threshold}_income"] = delta[seat]
            else:
                one.update(payments=delta[seat], other_first_hu=1)
        require(one["net"] == one["ordinary_hu_income"] + one["large_hu_income"] + one["payments"], "积分分账不相等")
        for ledger in (overall, dealer if dealer_seat == seat else non_dealer):
            for key in ACCOUNT_KEYS:
                ledger[key] += one[key]
        before = end
    result = {**overall, **{"dealer_" + k: v for k, v in dealer.items()},
              **{"non_dealer_" + k: v for k, v in non_dealer.items()}}
    require(overall["hands"] == 8 and overall["own_hu"] + overall["other_first_hu"] + overall["draws"] == 8,
            "八单局终局分账不完整")
    return result, before
