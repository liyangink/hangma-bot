"""独立自摸竞速I1：不带旧父代源码，验证向听阶段与有效牌支持的连贯比较。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import strong_seed_batch as b
import strong_seed_results as results

OUT = b.HERE / "selfdraw-tempo-20260920"
NAME = "selfdraw-tempo-terra-max"


def prepare():
    """冻结一份独立作者、一次错误修复和开发预算；不因负效果延长。"""
    if OUT.exists():
        raise ValueError("已存在提案目录，不覆盖")
    OUT.mkdir()
    sub = OUT / NAME
    sub.mkdir()
    instruction = '''本次是独立I1，不提供父代源码或历史效果分数。请交付一份连贯的完整动作评分算法，研究“杭麻自摸竞速”：不同向听阶段的有效牌数量应如何比较，怎样区分接近听牌、已经听牌和远离听牌的进展价值。
你可以选择分阶段非线性势能、同窗相对效率或其他有明确依据的结构，不指定公式或常数。需要有实质的决策依据，不能只把线性向听/有效张数换一组系数。范围允许重新组织基础牌效与动作机会代价；不要求与既有策略相似，也不要求只打破平分。优先形成单一可解释主机制，避免堆叠互不相关的奖金。若认为题设假设不成立，可以否定并选择同范围内更合理的竞速量。
目标为完整阶段前二效用group_advance_v1；不能用改选次数、胡牌次数或局部番数代替效果。当前阶段位置可以作为显式代理，但不能虚构剩余桌数、名次概率或他家手牌。只使用后附合同字段，输入view已经是纯字典映射，不调用view.candidate_view()，不导入生产模块，不写类型注解。
规则依据为项目冻结官方指南v34及唯一规则实现：只自摸，无点炮和抢杠胡；因此“防放铳”不成立，但喂牌可能帮助对手吃碰提速。普通型与七对资格、财神、财飘/爆头/杠链、抓打圈均只消费已经生产的事实；别种麻将的经验不能代替杭麻规则。不得重算向听、胡牌、合法性和结算，也不猜未来牌墙。
直接有效牌的remaining_estimate是4张上限减本人和公开可见牌后的未见张数，不是牌墙中的真实数量，更不是已经校准的摸牌概率。请解释所用效率量的单位、单调性、上界与失败场景；不把未知的后续向听变化或生存时间算成精确期望。若使用wall_remaining，保留20张以及行动顺序只是必要限制，不能承诺本人一定还能摸牌。允许不用牌墙字段，但请明确。
所有动作必须完整评分。相同口径的直接牌效和吃碰后弃牌分支必须可比，互斥的后续弃牌不能叠加收益。followup_branches只属于吃碰后的合法弃牌，不含普通弃牌后的下一摸再弃两步前瞻。条件路线是动作及对应弃牌后、无人先结束且本人摸到所列牌即胡的结算见证，不是立即收益；不同条件或弃牌不能相加。缺分支分析不抹掉独立成功的直接事实或条件路线，缺路线不伪造关闭。选择不使用部分字段是允许的，但须说明。
当前主任务不研究弃胡续飘：有合法立即胡时保留胡最高排序层，且要高于任意已知代理分。未知/无事实动作必须严格低于已知最终最低分；全未知时显式ABSTAIN。布尔值不可冒充向听、支持或结算数字。排序骨架/拒绝过滤/合法保底保持现行合同。
完整可见手牌my_hand不包含独立drawn_tile；若构造弃牌后结构，副露组数m，摸牌非空时my_hand为13-3m张，追加摸牌一次，即使牌码重复；无独立摸牌且待弃时14-3m张。恰好减一张候选弃牌，勿用集合去重。形状异常时仅退化依赖该信息的机制，不把独立已知事实抹掉。可以不用手牌结构；不要为了覆盖字段再加旧式几何连接分。
性能：努力满足默认100000次计数。实际仅因操作计数超额时，监督者可在新身份下用有界200000研究配置评价；其余输出、数值、结构、安全与信息权限限制不放宽。不得在源码中自行切换额度、捕获监管异常、隐藏计算或查询外部服务。说明最坏动作数/分支数的工作量上界与可简化热点；不以“以后编译”替代证据。
交付正式I1四字段及完整受限Python源码。机制说明包含：主假设、可见字段、评分公式与单位、触发和反例、可移除的消融方式、至少三个独立手算（不同向听支持取舍、已听/未听、吃碰与过牌同刻度）、未知和全未知边界、胡层和最大工作量。不要声称已经测试或预报提分。监督者会独立核对算术与生产choose行为，再冻结完整H/M评价；效果差不会得到调参修复。
'''
    if len(instruction) > 12000:
        raise ValueError("监督备注过长")
    panel = b.HERE / "real-behavior-panel-v1/panel.json"
    auth = b.unified_document(batch_label=NAME, authorization_id="r10-" + NAME,
        accounts={"tokens_input": 393216, "tokens_output": 131072, "tables_full": 300,
                  "tables_partial": 8, "prefix_generation": 8},
        issued_by="lead", issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth.update(generation_call_limits={"tokens_input": 196608, "tokens_output": 65536},
        max_model_calls=2, max_proposals=2, repair_calls_count_in_total=True,
        wall_clock_limit_seconds=14400, author_channel="codex_native_subagent",
        requested_model="gpt-5.6-terra", requested_reasoning_effort="max",
        autonomous_admission=False, author_feedback_mode="compact_prefix_v1",
        supervisor_feedback=instruction,
        issuance_basis="用户持续推进及Terra max原生作者授权；一份独立自摸竞速I1",
        scope="源码与算术通过后256自然桌+至多4条件桌；独立确认0，不发布",
        development_behavior_panel={"path": str(panel), "panel_digest": b.behavior.load_panel(panel)[0]})
    b.write(sub / "authorization.json", auth)
    b.write(OUT / "manifest.json", {"schema": "selfdraw-tempo-batch/1",
        "created_at_utc": b.search.utc_now(), "model": "gpt-5.6-terra", "effort": "max",
        "operator": "i1", "parent": None, "primary_comparator": "stable_v2",
        "initial_authors": 1, "max_author_calls": 2, "max_native_turn_seconds": 1800,
        "native_tokens": "unknown; conservative reservations are not actual usage",
        "core_panel_seed": 2026092001, "roots_per_mix": 8, "opponents": ["H", "M"],
        "seats": 4, "core_natural_tables": 256, "conditional_tables_limit": 4,
        "selection_rule": "H/M相对稳定V2均正且等权平分识别差下界正才签发第二已见开发清单；内部失败另审计，不抹去机制价值",
        "repair_rule": "只允许一次实际合同/数学实现错误修复；负效果不修复、不扫相邻常数",
        "purpose": "独立自摸竞速机制；不是既有几何结构项第三次修补",
        "confirmation_roots": 0, "release_eligible": False})
    state = b.search.av_start_iteration(sub / "run", operator="i1", generation_mode="delegate",
        predicate="branch_open", opponent="H", natural_roots=8, natural_seats=4,
        prefix_source="v2_behavior", panel_seed=2026092001, authorization=auth,
        archive_in={"source": "empty", "path": None, "applied_operator": "i1",
                    "note": "监督选择独立机制方向，非自动档案选父"})
    if state.get("stop_reason"):
        raise ValueError(state["stop_reason"])
    result = b.search.av_iteration_advance(b.search.av_latest_state_path(sub / "run"), sub / "run",
        authorization=auth, stop_after="BEHAVIOR_CHECKED")
    if not result.get("waiting_for_reply"):
        raise ValueError(str(result))
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / "run"))
    prompt = b.Path(state["generation"]["pending_dir"]) / "prompt.txt"
    b.write(sub / "author-task.json", {"model": "gpt-5.6-terra", "effort": "max", "task": "i1",
        "prompt": str(prompt), "prompt_sha256": b.digest(prompt.read_bytes()),
        "reply_path": str(sub / "author-reply.txt")})
    print("prepared", len(prompt.read_text()), flush=True)


def close():
    """按冻结V2对照和完整结果核验结案，不把独立I1伪称有父代增量。"""
    sub = OUT / NAME
    results.summarize(NAME, candidate_dir=sub, parent_specs={})
    closure = b.read(sub / "batch-closure.json")
    # 本次没有父代重放；共享汇总器的旧默认值不适用于独立I1。
    closure["common_v2_arms_reproduced"] = None
    closure["parent_reproduction_scope"] = "不适用：没有历史父代；仅核验本提案配对V2臂"
    b.write(sub / "batch-closure.json", closure)
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / "run"))
    bounds = {}
    for mix in ("H", "M"):
        panel = b.read(b.Path(state["iter_dir"]) / ("natural-" + mix) / "panel.json")
        stats = next(iter(panel["statistics"]["by_candidate"].values()))["panels"]["normal"]["panels"][mix]
        bounds[mix] = stats["delta_bounds"]
    low = sum(row["mean_delta_low"] for row in bounds.values()) / 2
    high = sum(row["mean_delta_high"] for row in bounds.values()) / 2
    positive = low > 0 and all(row["mean_delta"] > 0 for row in closure["versus_v2"].values())
    reviews = [row["execution_review"] for row in b.read(sub / "full-result-reconciliation.json")["results"]]
    clean = all(row["zero_internal_failures_verified"] for row in reviews)
    b.write(sub / "development-decision.json", {
        "effect_condition_passed": positive,
        "zero_internal_failures_verified": clean,
        "continue_second_seen_panel": positive and clean,
        "effect_positive_needs_execution_review": positive and not clean,
        "equal_mix_identification_low": low, "equal_mix_identification_high": high,
        "interval_kind": "平分识别区间，非置信区间",
        "performance_policy": "正效果但内部失败时保留研究价值，另审计/冻结研究配置后推进，不抹去成绩",
        "release_eligible": False, "primary_comparator": "stable_v2"})
    print("effect_condition_passed", positive, "execution_clean", clean, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "ingest", "evaluate", "close"))
    args = parser.parse_args()
    if args.operation == "prepare": prepare()
    elif args.operation == "close": close()
    else:
        b.BATCH = OUT
        b.advance(NAME, args.operation == "evaluate")
