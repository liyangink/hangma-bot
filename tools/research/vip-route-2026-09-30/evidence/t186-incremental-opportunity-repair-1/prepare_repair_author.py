"""准备T186两作者上限及新来源；先读闭合路径，不调用模型或模拟器。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

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
import json
import secrets
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, canonical, pin, save
from prepare_author import wait_summary
from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """沿用原规则与操作额；新独立来源在作者调用前封存，不给作者读取。"""
    batch_data = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-BATCH.json")).read_text())
    batch_data["batch_id"] = "t186-two-author-incremental-opportunity-20261005"
    batch_data["budgets"].update(model_calls=2, input_tokens=2097152, output_tokens=131072, wall_clock_seconds=1800)
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), batch_data)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent = _project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-incremental-model-output")
    parents = load_vip_parents([parent], batch)
    status = json.loads((_project_file(_PROJECT_ROOT, HERE / "confirmation-paths/CLOSED.json")).read_text())
    assert status["complete"] and status["returncodes"] == [0] * 4
    rows = [json.loads(l) for l in (_project_file(_PROJECT_ROOT, HERE / "confirmation-paths/rows.jsonl")).read_text().splitlines()]
    public = {}
    for slot in range(4):
        with gzip.open(_project_file(_PROJECT_ROOT, HERE / f"confirmation-paths/worker-{slot}/public-first-rows.jsonl.gz"), "rt") as stream:
            for line in stream:
                row = json.loads(line)
                public[row["ordinal"]] = row
    classes, groups = {}, defaultdict(Counter)
    for row in rows:
        if row.get("switch") != "discard->hu":
            continue
        a, b = row["parent_hand"], row["child_hand"]
        label = ("wait_lost" if a["fan_if_own_hu"] is None else "same_fan"
                 if a["fan_if_own_hu"] == b["fan_if_own_hu"] else "stop_lower_fan")
        classes[row["ordinal"]] = label
        groups[label]["pairs"] += 1
        groups[label]["associated_first_hand_net"] += row["hand_delta"]["net"]
        groups[label]["associated_table_net"] += row["table_delta"]["net"]
    save(_project_file(_PROJECT_ROOT, HERE / "EARLY-HU-PATH-SUMMARY.json"), {"groups": dict(groups),
        "source_file_pin": pin(_project_file(_PROJECT_ROOT, HERE / "confirmation-paths/rows.jsonl")),
        "same_source_rotations_correlated": True, "path_outcome_not_causal_action_effect": True})
    # 全88个已可胡首分歧，加各类弃牌首分歧首6个不同母源，不按高分挑题。
    selected = set(classes)
    for sign in ("negative", "zero", "positive"):
        used = set()
        for row in rows:
            net = row["hand_delta"]["net"] if "hand_delta" in row else None
            if row.get("switch") != "discard->discard" or row["root_id"] in used:
                continue
            category = "negative" if net < 0 else "zero" if net == 0 else "positive"
            if category == sign:
                selected.add(row["ordinal"])
                used.add(row["root_id"])
                if len(used) == 6:
                    break
    originals = [c for name in ("CASES.json", "SUPPLEMENT-CASES.json")
                 for c in json.loads((_project_file(_PROJECT_ROOT, PRIOR / name)).read_text())["cases"]]
    new_cases = []
    for ordinal in sorted(selected):
        row, raw = rows[ordinal], public[ordinal]["parent_original_row"]
        new_cases.append({"label": f"closed-confirmation:{ordinal:03d}", "root_id": row["root_id"],
            "classes": [classes.get(ordinal, "discard_path"), "exposed_development_only"],
            "observation": raw["observation"], "window_key": raw["window_key"],
            "expected_view_sha256": raw["scoring_calls"][0]["input_capture"]["view_sha256"],
            "S02_first": raw["selected_action_key"], "original_S02_entries": raw["candidates"]})
    save(_project_file(_PROJECT_ROOT, HERE / "CASES.json"), {"cases": originals + new_cases, "new_confirmed_path_cases": len(new_cases),
        "purpose": "公开机械及机制开发；没有独立强度或固定必须选的动作标签"})
    examples, used_sources = [], set()
    for kind, limit in (("stop_lower_fan", 6), ("wait_lost", 6), ("same_fan", 4)):
        count = 0
        for row in rows:
            ordinal = row["ordinal"]
            if classes.get(ordinal) != kind or row["root_id"] in used_sources:
                continue
            raw = public[ordinal]["parent_original_row"]
            digest = raw["scoring_calls"][0]["input_capture"]["view_sha256"]
            location = _project_file(_PROJECT_ROOT, PRIOR / "natural-confirmation" / f"root-{row['root_index']:03d}" / f"seat-{row['rotation']}-arm-0")
            view = None
            with gzip.open(location / "views.jsonl.gz", "rt") as stream:
                for line in stream:
                    record = json.loads(line)
                    if record["view_sha256"] == digest:
                        view = record["view"]
                        assert hashlib.sha256(canonical(view)).hexdigest() == digest
                        break
            assert view is not None
            nodes = {n["node_key"]: n for n in view["nodes"]}
            roots = [{"action": a, "node_kind": nodes[a["node_key"]]["kind"],
                      "settlement": nodes[a["node_key"]]["settlement"],
                      "waiting_summary": wait_summary(nodes[a["node_key"]]["waiting"], view["visible_state"]["seat"])}
                     for a in view["actions"]]
            examples.append({"label_for_development_only": f"contrast-{len(examples) + 1}",
                "historical_path_class_not_action_label": kind, "visible_state": view["visible_state"],
                "direct_roots_summary_not_full_DTO": roots, "view_sha256": digest,
                "original_scores": {k: row[k] for k in ("parent_scores", "child_scores")},
                "boundary": "公开状态/原评分；不提供后继手牌、牌墙、隐藏样本或确认种子；历史结果不是此动作EV"})
            used_sources.add(row["root_id"])
            count += 1
            if count == limit:
                break
    seeds = set()
    for name in ("DEVELOPMENT-PLAN.json", "CONFIRMATION-PLAN.json"):
        seeds.update(r["seed"] for r in json.loads((_project_file(_PROJECT_ROOT, PRIOR / name)).read_text())["roots"])
    fresh = []
    for index in range(192):
        value = secrets.randbits(63)
        while value in seeds:
            value = secrets.randbits(63)
        seeds.add(value)
        fresh.append({"root_id": f"t186-fresh-{index + 1:03d}", "seed": value})
    compositions = freeze_qualifier_compositions(fresh, 0.6)
    save(_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"), {"development": compositions[:64],
        "independent_confirmation": compositions[64:], "wall_generated": False, "models_calls": 0,
        "not_in_author_prompt": True, "confirmation_requires_separate_frozen_budget_admission": True})
    feedback = {
        "human_objective": "继承同速自然面子及进张前沿；有真实大牌收益时可承担合理普通效率损失。重点让已有多白从百搭转为番值，而非只追下一张新白。",
        "reference_baseline": "线上T110-S02；本次正式m1父为9adb888c，未准入",
        "closed_confirmation_aggregate": {"net_per_complete_table": 4.912109375,
            "net_cluster95": [-1.623095703125, 11.705078125], "ordinary_income": 7.265625,
            "large_income": -3.203125, "payments": 0.849609375, "not_admitted": True},
        "first_divergence_early_hu": dict(groups), "examples": examples,
        "mechanism_gap": "10次少番中9次当时持>=2白，目标自然need常为1或2，并非全是need=0误删。已有白从百搭释放给爆头/财飘，与未来再摸白是不同增量；原父用need/(1+need)乘总option gain仍是代理，不是未来支付增量。不能只修零need或只加再白用途。相同白数和墙余中也有等待失胡负例，不能按白数硬等。",
        "requested_mechanism": "联合比较：当前Hu已实现的支付/白用途；同码下一摸真实支付差；当前已持白经自然成型后释放的新增用途；未来新增白的另一种可选增量。去除成熟单白爆头重复信用。自然改善的库存、码宽、需求/弃白步骤、普通胡出口维持、墙余/庄位/副露风险共同折价；同一机会不可跨通道相加重计，未知不当零或保证。需要有跨来源差异，不能只改说明或缩放所有得分。可重设计联合公式，不按事后胜负硬编码。",
        "negative_controls": "等待失胡34处含11处双白，与10处少番相互制约。成熟单白已两番且下一摸全同支付的原T183锚点，不可再次重复奖励已成形爆头；已有普通/七对/自然准备全115窗仍须通过。",
        "other_family_reference_source": (_project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-white-increment-model-output/candidate.py")).read_text(),
        "other_family_boundary": "此源码不是正式第二父代；开发净+7.1172仍跨零，大牌收入负；只能作额外白增量实现参考，不能照搬为已有效方案。",
        "evaluation_budget": "新批最多两次作者。先221个左右公开机械/正负窗、再有限条件续打；完整桌按8/16/32来源阶段开发，至少4进程。没有自动大确认；需新块复现和更强净信号后事前单独封存确认计划。",
        "contract_reminder": "全部合法根每根一个有限score和有界trace；changed_branches为非空字符串。禁止import/while/递归/list.extend/下标赋值/默认参数/注解；禁止牌局ID/标签/期望动作特判。排序点不是概率或期望分，保留全节点类型和公开信息边界。",
    }
    with (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-REPAIR-FEEDBACK.txt")).open("x") as stream:
        stream.write(json.dumps(feedback, ensure_ascii=False, allow_nan=False))
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "CASES.json"), _project_file(_PROJECT_ROOT, HERE / "EARLY-HU-PATH-SUMMARY.json"),
             _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-REPAIR-FEEDBACK.txt"),
             parent / "candidate.py", parent / "generation.json", _project_file(_PROJECT_ROOT, HERE / "confirmation-paths/CLOSED.json")]
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), {"complete": True, "files": {str(p): pin(p) for p in files},
        "formal_parent": parents[0]["identity"], "maximum_author_calls": 2,
        "mechanical_views": len(originals + new_cases), "public_examples": len(examples),
        "new_scores_worlds_tables_models_HTTP": 0, "cpu_worker_count_next_tables": 4,
        "large_confirmation_automatic_dispatch": False})
    print(json.dumps({"complete": True, "mechanical_views": len(originals + new_cases),
        "public_examples": len(examples), "model_calls": 0}), flush=True)


if __name__ == "__main__":
    main()
