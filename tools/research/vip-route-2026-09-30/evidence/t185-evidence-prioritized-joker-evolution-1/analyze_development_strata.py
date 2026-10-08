"""完整开发闭合后按0—4起手白数分层；收入分账与父参考层贡献均须对总净分。"""

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
import gzip
import json
from pathlib import Path

from common import HERE, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import background_priority, postprocess_lock, require_development_dispatch


def blank():
    """能力分层计数；速度单位为摸打决策次数（含补牌），不是全桌巡数。"""
    return dict.fromkeys(("hands", "own_hu", "dealer_hands", "dealer_hu", "net", "ordinary_hu_income",
        "large_hu_income", "payments", "white_value_hu", "baotou_hu", "piao_hu", "four_white_hu",
        "own_hu_draw_decisions_including_replacements", "dealer_transitions_observed", "dealer_held"), 0)


def white_value_details(details):
    """只据已有生产结算明细识别番值白板；单纯百搭或纯杠开不计该能力。"""
    dev.require(type(details) is list and all(type(s) is str for s in details), "结算明细未知")
    baotou = "爆头" in details
    four_white = "4个白板" in details
    piao = any(s in ("财飘", "双财飘", "三财飘") or s.startswith(("连飘×", "杠飘链×")) for s in details)
    return {"white_value_hu": int(baotou or piao or four_white), "baotou_hu": int(baotou),
            "piao_hu": int(piao), "four_white_hu": int(four_white)}


def metrics(settlement, seat):
    """只对已核结算做指标分账，胡牌与支付规则仍由生产结算提供。"""
    row = blank()
    row["hands"] = 1
    row["dealer_hands"] = int(settlement["dealer_seat"] == seat)
    row["net"] = settlement["score_delta"][seat]
    if not settlement["is_draw"]:
        if settlement["winner_seat"] == seat:
            row["own_hu"] = 1
            row["dealer_hu"] = row["dealer_hands"]
            row["ordinary_hu_income" if settlement["fan"] < 4 else "large_hu_income"] = row["net"]
            row.update(white_value_details(settlement["details"]))
        else:
            row["payments"] = row["net"]
    dev.require(row["net"] == row["ordinary_hu_income"] + row["large_hu_income"] + row["payments"], "分层净分不对账")
    return row


def add(target, row):
    """相同单位的计数相加，比例只在完整分母闭合后生成。"""
    for key, value in row.items():
        target[key] += value


def rates(row):
    """没有可观测分母时返回未知；不同层不以零补缺或冒称因果能力。"""
    def ratio(n, d):
        return None if row[d] == 0 else row[n] / row[d]
    return {"hu_per_hand": ratio("own_hu", "hands"), "dealer_hu_per_dealer_hand": ratio("dealer_hu", "dealer_hands"),
        "white_value_hu_per_own_hu": ratio("white_value_hu", "own_hu"),
        "white_value_hu_per_hand": ratio("white_value_hu", "hands"),
        "mean_own_hu_draw_decisions_including_replacements": ratio("own_hu_draw_decisions_including_replacements", "own_hu"),
        "dealer_held_per_observed_transition": ratio("dealer_held", "dealer_transitions_observed")}


def main():
    """不能读中途分；完整读回通过后生成解释报告，不另改选择或确认门。"""
    background_priority()
    with postprocess_lock("development_white_strata"):
        require_development_dispatch()
        closed, closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"))
        plan, plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
        dev.require(closed["complete"] and closed["actual_table_instances"] == 512 and
            closed["files"][str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))] == plan_pin, "开发未完整闭合")
        dev.frozen(plan)
        arms = [plan["parent"], *plan["candidates"]]
        actual = [{str(n): blank() for n in range(5)} for arm in arms]
        hands, files = {}, {str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json")): closed_pin,
            str(Path(__file__)): pin(Path(__file__))}
        for table in closed["tables"]:
            index = next(i for i,r in enumerate(plan["roots"], 1) if r["root_id"] == table["root_id"])
            rotation, arm_index = table["rotation"], table["arm_index"]
            directory = _project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}")
            closure_file = directory / "CLOSURE.json"
            receipt_file = directory / "focal-decisions.jsonl.gz"
            for path in (closure_file, receipt_file):
                dev.require(pin(path) == closed["files"][str(path)], "开发分层原件漂移")
                files[str(path)] = pin(path)
            closure, _ = dev.read(closure_file)
            draw_decisions = dict.fromkeys(range(1,9), 0)
            with gzip.open(receipt_file, "rt") as stream:
                for raw in stream:
                    row = dev.decode(raw)
                    round_no = row["observation"]["round_no"]
                    if row["phase"] == "draw":
                        draw_decisions[round_no] += 1
            for round_no, (exported, proof) in enumerate(zip(closure["settlements"], closure["pairing_proofs"]), 1):
                white = dev.integer(proof.get("focal_initial_white_count"), "实际起手白数", 0)
                dev.require(white <= 4 and proof["teacher_only_not_policy_input"], "起手白数或权限不符")
                row = metrics(exported["settlement"], rotation)
                if row["own_hu"]:
                    row["own_hu_draw_decisions_including_replacements"] = draw_decisions[round_no]
                if round_no < 8 and row["dealer_hands"]:
                    row["dealer_transitions_observed"] = 1
                    row["dealer_held"] = int(closure["pairing_proofs"][round_no]["dealer_seat"] == rotation)
                hands[(index, rotation, arm_index, round_no)] = (white, row)
                add(actual[arm_index][str(white)], row)
            dev.require(sum(hands[(index,rotation,arm_index,n)][1]["net"] for n in range(1,9)) == table["account"]["net"],
                "原桌分层积分与完整桌不一致")
        reference = []
        for arm_index, arm in enumerate(arms[1:], 1):
            layers = {str(n): {"net": 0, "ordinary_hu_income": 0, "large_hu_income": 0, "payments": 0} for n in range(5)}
            for i in range(1,33):
                for r in range(4):
                    for n in range(1,9):
                        white, parent = hands[(i,r,0,n)]
                        _, child = hands[(i,r,arm_index,n)]
                        for key in layers[str(white)]:
                            layers[str(white)][key] += child[key] - parent[key]
            comparison = closed["candidates"][arm_index-1]
            dev.require(sum(v["net"] for v in layers.values()) == comparison["net_delta_sum_128_tables"], "父参考层贡献不对总净差")
            reference.append({"candidate_id": arm["identity"]["candidate_id"], "parent_reference_strata_delta_sums": layers,
                "per_complete_table_contribution": {w:{k:v/128 for k,v in layer.items()} for w,layer in layers.items()},
                "interpretation": "按父该单局起手白数固定分层；包含后继庄权和配牌变化，不能解释为控制了财神数量的直接因果效应"})
        result = {"complete": True, "files": files, "new_scores_worlds_tables": 0,
            "arms": [{"candidate_id": arm["identity"]["candidate_id"], "strata": {w:{"counts":v,"rates":rates(v)}
                for w,v in layers.items()}} for arm,layers in zip(arms,actual)], "paired_reference_contributions": reference,
            "speed_unit": "本家摸打评分决策次数，含杠／飘补牌，不冒称全桌巡数",
            "white_value_definition": "生产结算明细爆头／财飘／混合杠飘链／四白加番；只作百搭不计",
            "stratum_rates_are_descriptive_not_strength_gates": True}
        dev.require(sum(v["hands"] for layer in actual for v in layer.values()) == 4096, "分层单局分母不等于4096")
        dev.frozen(plan)
        dev.require(all(pin(Path(p)) == h for p,h in files.items()), "分层过程中原件漂移")
        save(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-JOKER-STRATA.json"), result)
    print(json.dumps({"complete": True, "hand_instances": 4096, "new_scores_worlds_tables": 0}))


if __name__ == "__main__":
    main()
