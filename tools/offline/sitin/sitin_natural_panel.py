# -*- coding: utf-8 -*-
"""E 批次自然开局面板（natural panel）编排：正常阶段双臂配对评估（v4 §7.1/§11）。

规范来源：review/llm-guided-heuristic-route-2026-09-15/SEARCH-SPACE-REDESIGN-2026-09-16.md
§7.1（面板构造）、§11（费用账）与 contracts/group-dev-v1.json（四人单组、每阶段
tables_per_group 桌、H/M 对手情景、group_advance_v1 目标）。

本脚本是**独立编排件**：复用 sitin_stage 的场次计划（build_table_plan/
rotate_permutation/derive_seed）、名次分（place_points_for_table）与目标求值
（group_advance_utility/LedgerRow）的单一实现，不修改 sitin_stage.py；桌赛执行走
offline.evaluate.drive_match（与 sitin_stage.execute_table 同一组合根运行时与驱动，
差别只在策略按臂注入：focal 座位候选臂=ActionValuePolicy(候选源码)/基线臂=
weighted_heuristic_v2，其余座位按合同 opponent_scenarios 装配）。

红线（派单逐条落地，机器可核）：
  - focal 之外座位两臂策略**完全一致**（同一 build_panel_policy 白名单装配）；
  - 双臂同 panel_seed：table_id/seed 只由（panel_seed、对手、根、焦点座位、桌号）
    派生，**不含臂标识**——同根两臂拿到同一随机映射与牌墙（配对可比）；
  - 任一臂执行失败按 T16 **整根标 invalid**（Q4：基线臂与候选臂同权；该根全部
    座位样本 completeness=invalid，数值保留但不冒充可用），费用照记；统计先验
    冻结期望双臂/座位/赛程清单（每样本 root_expected），任一臂失败/漏行/重复行
    使整根失效，不用剩余座位算选择值；
  - 根身份绑定生成器与 panel_seed（Q7：source_root_id 形如 np-{对手}-{seed}-rootNN，
    table_id 同带 seed 段），并写 root_content_digest 供统计器拒绝同 ID 不同内容；
    **禁止**沿用 batch8 手工给 root_id 加 "-r2" 后缀的做法——那是目录名补丁，
    新批次必须换 panel_seed 或根序号；
  - 不读 WorldState 私有状态：只经 drive_match 的公开 PlayerObservation 驱动。

费用账（v4 §11）：tables_full 按**每臂每座位每阶段 tables_per_group 桌**计
（缺省 4 座位 × 2 臂 × 2 桌 = 每根 16 桌）；token 恒 0（无 LLM 调用）；墙钟/CPU
秒分列。台账走 sitin_search.ActionValueLedger（可选 --ledger 追加到既有账本）。

用法：

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_natural_panel.py \
        --candidate-source <candidate.py> --opponent H --roots 1 \
        --contract-file review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json \
        --authorization .team-work/tasks/sitin-phase3-v4/llm-authorization.json \
        --out <evidence>/natural-H

按根选取（P2b：档案挑战补根，只评参与者缺失的那些根，不整前缀重跑）：

    # 根索引列表（与 --roots 互斥；根身份与按根数取前缀逐字节一致）
    ... --root-indices 3,4,5,6 --out <evidence>/natural-H-roots3to6

    # 或根种子列表（每项必须能唯一回落到某根序号，见 natural_root_selection）
    ... --root-seeds <seed3>,<seed4> --out <evidence>/natural-H-seeds34
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import hashlib
import inspect
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
_HERE = Path(__file__).resolve().parent
for _entry in (str(_project_file(_PROJECT_ROOT, REPO / "src")), str(_HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import sitin_stage as stage  # noqa: E402
import sitin_execution_audit as execution_audit  # noqa: E402
import sitin_execution_profile as execution_profiles  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    BOOTSTRAP_RUNTIME_HOOK,
    MatchDriverConfig,
    MatchExperiment,
    MatchSeedSpec,
    PolicyDeclaration,
    StageSituationProjection,
    build_match_result,
    drive_match,
    seat_policies_from,
)
from hangma_bot.offline.evaluation_results import compute_rules_hash  # noqa: E402
from sitin_archive import paired_stage_statistics  # noqa: E402

#: 面板产物 schema。
NATURAL_PANEL_SCHEMA = "sitin-natural-panel/1"
#: 样本 schema（与 C1/C2 样本同形，sitin_archive.classify_sample 可直接消费）。
NATURAL_SAMPLE_SCHEMA = "sitin-action-value-sample/1"
#: 焦点参赛者身份（阶段账本里的 participant_id；两臂同名，配对求值用）。
FOCAL_PARTICIPANT = "focal"
#: 基线臂 focal 策略（合同 panel.policy_pool 白名单成员；两臂对手同源装配）。
BASELINE_FOCAL_POLICY = "weighted_heuristic_v2"
#: 缺省面板种子（与合同 seeds.panel_seed 同值）。
DEFAULT_PANEL_SEED = 20260916
#: 缺省合同路径（相对仓库根）。
DEFAULT_CONTRACT = "review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json"
#: action_value_v1 输入输出合同（candidate_id 绑定用；相对仓库根）。
AV_CONTRACT = "review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json"
#: 自然面板生成器/口径版本（M1）：v1 = R6 冻结口径（每桌不注入阶段账，第二桌
#: 读不到首桌形成的阶段积分与名次分）；v2 = 每桌开始前按「参赛者身份 → 物理
#: 座位」注入已完成桌阶段账（复审 §5 M1 修复）。
NATURAL_PANEL_GENERATOR = "natural-opening-panel-v2"
#: 阶段账注入口径（合同 identity 项 stage_projection：投影方式变更即新实验身份）。
STAGE_ACCOUNT_MODE = "per_table_completed_account_v1"
#: 显式根选取的根序号上界（P2b）：根身份把根序号渲染成两位字段
#: （np-{对手}-{panel_seed}-rootNN），越界会让身份字段宽度漂移（root100），
#: 按固定宽度解析或人工核对根清单的下游会失配；因此显式选择一律限制在 1..99。
MAX_ROOT_INDEX = 99


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
                    + "\n", encoding="utf-8")


def require_authorization(token: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """真实执行预算门：走**统一的受信授权校验入口**（Q6；P14 收口）。

    为什么不再各写一份判据：旧实现是 `authorized is True and batch == 7`——只认一个
    历史门值，既不校验"这一批是哪个标签"、也不校验"本次操作是否在允许集内/账户额度
    是否够/签发方是否受信"；而状态机（`sitin_search._step_natural`）早已改走
    `av_authorization_allows(operation="natural_panel")`。同一个操作被上下两层用两套
    判据判，越权或未受信的令牌可以绕过状态机、直接从本模块入口混进真实桌赛。

    现在**转发到同一个函数**（其唯一实现坐落在 `sitin_opportunities
    .av_authorization_check`）：身份（authorization_id）/批次标签（batch_label）/
    trusted/允许操作集（模型无权修改）/账户额度逐项核对；legacy 形态（无
    `sitin-authorization/1` 字段、authorized=true 且 batch==7）按**同范围**接受并在
    审计里标 `authorization_form=legacy_batch7`（含移除条件），旧令牌因此照跑。

    返回校验结论（authorization_form / authorization_id / batch_label /
    allowed_operations / allowed_accounts / problems …），调用方应原样写进产物与
    交接件。失败关闭：任一问题项即 SystemExit——一张桌都不启动。
    """

    try:
        from sitin_search import (AV_AUTHORIZATION_OPERATION_REQUIREMENTS,
                                  av_authorization_allows)
    except ImportError as error:
        # 装载不到受信校验入口 ⇒ 失败关闭：**不退回**旧式 authorized/batch 判据
        # （那正是本包要收掉的"两套判据"，退回等于给越权令牌留一条侧门）。
        raise SystemExit(
            "自然面板真实执行无法装载受信授权校验入口（sitin_search."
            "av_authorization_allows）：{0}。fail-closed，不启动任何桌赛实例。"
            .format(error))
    ok, refusal, verdict = av_authorization_allows(
        token, operation="natural_panel",
        required=AV_AUTHORIZATION_OPERATION_REQUIREMENTS["natural_panel"])
    if ok:
        return verdict
    raise SystemExit(
        "自然面板真实执行未取得**受信**授权（Q6 统一校验入口 sitin_search."
        "av_authorization_allows，operation=natural_panel）：{0}。"
        "授权形态见 sitin-authorization/1（字段：authorization_id/batch_label/trusted/"
        "allowed_operations/allowed_accounts/issued_by/issued_at_utc）；原「批次 7」"
        "同范围复验按 legacy 形态继续接受（authorized=true 且 batch=7，审计记 "
        "authorization_form=legacy_batch7）。fail-closed：不启动任何桌赛实例。"
        .format(refusal))


def natural_root_seed(panel_seed: int, opponent: str, root_index: int) -> int:
    """根种子：只由（panel_seed、对手、根序号）派生，两臂共用。"""
    return stage.derive_seed(int(panel_seed), "natural", str(opponent),
                             "root", str(root_index))


def natural_root_id(opponent: str, panel_seed: int, root_index: int) -> str:
    """根身份（Q7）：绑定对手混合、panel_seed 与根序号——np-{mix}-{seed}-rootNN。

    不同 panel_seed/生成器批次的根天然不同 ID；配合 root_content_digest 由
    统计器拒绝同 ID 不同内容（禁止 batch8 式手工目录后缀补丁）。
    """
    return "np-{0}-{1}-root{2:02d}".format(opponent, int(panel_seed), int(root_index))


def natural_table_id(opponent: str, panel_seed: int, root_index: int,
                     focal_seat: int, table_no: int) -> str:
    """桌身份（Q7）：table_id 同样携带 panel_seed 段，避免跨批次同名桌。"""
    return "np-{0}-{1}-r{2:02d}-s{3}-t{4}".format(
        opponent, int(panel_seed), int(root_index), int(focal_seat), table_no)


def natural_root_index_for_seed(*, opponent: str, panel_seed: int,
                                root_seed: int) -> int:
    """把根种子唯一回落到派生出它的根序号（P2b 显式根种子选取）。

    根种子**不是自由参数**：它恒等于
    natural_root_seed(panel_seed, opponent, 根序号)。因此显式给种子时必须能在
    1..MAX_ROOT_INDEX 中**唯一**命中某个序号：命中 0 个（未知种子）或 >1 个
    （种子歧义）一律拒绝——否则会出现「有种子、无根序号」的第二类根，而 P6 的
    实例台账按 root_id（来源根）计费，第二类根会重复计费或漏计。
    """

    wanted = int(root_seed)
    matches = [index for index in range(1, MAX_ROOT_INDEX + 1)
               if natural_root_seed(panel_seed, opponent, index) == wanted]
    if not matches:
        raise ValueError(
            "根种子 {0} 不是（对手 {1}、panel_seed {2}）派生的任何根种子：显式根"
            "种子必须能由 natural_root_seed 回落到 1..{3} 中的根序号".format(
                wanted, opponent, int(panel_seed), MAX_ROOT_INDEX))
    if len(matches) > 1:
        raise ValueError("根种子 {0} 同时对应根序号 {1}（种子歧义）：拒绝猜测根身份".format(
            wanted, matches))
    return int(matches[0])


def _root_count(value: Any) -> int:
    """校验旧接口根数：必须是非负 int（不做静默取整/静默取空）。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("根数 roots 必须是 int（不做静默取整），得到 {0!r}".format(value))
    if int(value) < 0:
        raise ValueError("根数 roots 必须 ≥ 0，得到 {0}（旧实现下负数会静默产出空"
                         "面板并把 planned_tables 记成负数）".format(value))
    return int(value)


def _root_int_list(value: Any, *, label: str) -> List[int]:
    """把选择参数折成 int 列表：非空、逐项整数（字符串/布尔/浮点一律拒绝）。"""

    if isinstance(value, bool) or isinstance(value, (str, bytes, Mapping)):
        raise ValueError("{0} 必须是整数列表，得到 {1!r}".format(label, value))
    try:
        items = list(value)
    except TypeError:
        raise ValueError("{0} 必须是整数列表，得到 {1!r}".format(label, value))
    if not items:
        raise ValueError("{0} 必须非空：空选择集无法定义要评价哪些根（旧接口的"
                         "空前缀行为只由 roots=0 表达）".format(label))
    collected: List[int] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError("{0} 的每一项必须是 int，得到 {1!r}（不做静默取整）".format(
                label, item))
        collected.append(int(item))
    return collected


def _canonical_root_indices(indices: Sequence[int], *, label: str) -> Tuple[int, ...]:
    """根序号规范化：区间内、无重复、升序（选择集语义=集合）。"""

    out_of_range = sorted({index for index in indices
                           if not 1 <= index <= MAX_ROOT_INDEX})
    if out_of_range:
        raise ValueError("{0} 越界：{1} 不在 1..{2}（根序号是根身份字段，越界即"
                         "身份漂移）".format(label, out_of_range, MAX_ROOT_INDEX))
    duplicates = sorted({index for index in indices if indices.count(index) > 1})
    if duplicates:
        raise ValueError("{0} 有重复根序号 {1}：同一根不得在一次调用里评价两次"
                         "（同一实例会被重复计费）".format(label, duplicates))
    return tuple(sorted(int(index) for index in indices))


def natural_root_selection(*, opponent: str, panel_seed: int,
                           roots: Optional[int] = None,
                           root_indices: Optional[Sequence[int]] = None,
                           root_seeds: Optional[Sequence[int]] = None) -> Tuple[int, ...]:
    """把三种根选择调用形式归一化成**规范根序号元组**（P2b 显式根选取）。

    缺陷来源（P7b 实测约束）：本面板原先只接受「根数 N」，只能复现某
    (mix, panel_seed) 的 root01..rootN **前缀**；档案挑战补根时无法只评「参与者
    缺失的那些根」，只能整前缀重跑——要么重复评价同一实例/重复计费，要么放弃
    新鲜独立根（A2「补根成功才换席」在真实运行中因此不可达）。

    三种形式（**恰好**给一个；多给或一个都不给都拒绝，不猜调用方意图）：

      - roots=N：取前缀 1..N（旧接口；N=0 明确定义为空选择，保持既有行为）；
        负数拒绝（旧实现下负数会静默产出空面板并把 planned_tables 记成负数）；
      - root_indices=[3,4,...]：显式根序号；非空、无重复、每项落在
        1..MAX_ROOT_INDEX；
      - root_seeds=[...]：显式根种子；每项必须能**唯一**回落到某根序号
        （见 natural_root_index_for_seed）。

    归一化口径：选择集语义=**集合**，返回值按序号升序——同一集合的任意书写顺序
    产出逐字节相同的产物与账本步标识（顺序不承载证据）。根身份仍只由
    (对手, panel_seed, 根序号) 决定，所以「按索引选根」与「按根数取前缀」对
    同一个根给出**同一** root_id/root_seed/table_id/root_content_digest：P6 的
    实例台账（来源根 × 座位 × 臂 × 赛程）才能把「同一个根」识别为同一实例
    （不重复计费）。
    """

    given = [name for name, value in (("roots", roots),
                                      ("root_indices", root_indices),
                                      ("root_seeds", root_seeds))
             if value is not None]
    if len(given) != 1:
        raise ValueError(
            "根选择必须恰好给出 roots / root_indices / root_seeds 之一，得到 {0}"
            "（根选择是计费身份的一部分，不做缺省猜测）".format(given or "一个都没有"))
    if roots is not None:
        return tuple(range(1, _root_count(roots) + 1))
    if root_indices is not None:
        return _canonical_root_indices(
            _root_int_list(root_indices, label="根索引 root_indices"),
            label="根索引 root_indices")
    resolved = [natural_root_index_for_seed(opponent=opponent, panel_seed=panel_seed,
                                            root_seed=seed)
                for seed in _root_int_list(root_seeds, label="根种子 root_seeds")]
    return _canonical_root_indices(resolved, label="根种子 root_seeds")


def natural_selection_token(root_indices: Sequence[int]) -> str:
    """选择集在账本步标识里的规范记号（P2b）。

    前缀选择（1..N，含旧接口 roots=N 与 roots=0）沿用旧记号 str(N)——既有账行的
    step_id 逐字不变；非前缀选择写作 idx3-4：补根是**不同**的任务身份，必须有
    自己的账行，否则会被前缀账行的结算（TaskAlreadySettled）挡住而无法补根。
    """

    selection = tuple(int(item) for item in root_indices)
    if selection == tuple(range(1, len(selection) + 1)):
        return str(len(selection))
    return "idx" + "-".join(str(item) for item in selection)


def build_stage_situation(*, plan: Any, table_no: int, tables_completed: int,
                          totals: Mapping[str, int], place_totals: Mapping[str, int],
                          rounds_per_game: int) -> StageSituationProjection:
    """当前桌执行前可注入的阶段处境投影（M1；单一实现）。

    - **阶段账 = 已完成各桌之和**：totals/place_totals 按参赛者身份（participant_id）
      累计，只含**当前桌之前**已完成的桌赛；当前桌进行中的积分在
      PlayerObservation.scores 里由驱动单独维护，不在此重复累计；
    - **身份 → 物理座位**：participant_ids_by_seat 直取计划的实际座位映射
      plan.seats()（= 按 plan.permutation 展开），换座后身份与座位仍一一对应；
    - **已完成/剩余赛程**：stage_table_no 为当前桌序（1 起）、tables_in_stage 为
      阶段总桌数、tables_completed 为已完成桌数 → 策略可推剩余桌数；
    - 只承载已完成桌的公开事实，不含未来结果或他家暗牌（T09 红线）。
    """

    participants_by_seat = tuple(str(item) for item in plan.seats())
    scores = tuple(int(totals.get(participant, 0)) for participant in participants_by_seat)
    places = tuple(int(place_totals.get(participant, 0))
                   for participant in participants_by_seat)
    return StageSituationProjection(
        stage_table_no=int(table_no),
        tables_in_stage=int(plan.tables_in_stage),
        stage_role=str(plan.stage_role),
        tables_completed=int(tables_completed),
        rounds_per_game=int(rounds_per_game),
        stage_scores_by_seat=scores,
        place_points_by_seat=places,
        participant_ids_by_seat=participants_by_seat,
    )


def build_seat_stage_plans(*, contract: Mapping[str, Any], opponent: str,
                           root_index: int, focal_seat: int,
                           panel_seed: int) -> List[Any]:
    """构造一个（根 × 焦点座位）的完整阶段计划：tables_per_group 桌。

    计划**与臂无关**：table_id/seed/permutation/参赛者/对手策略名都不含臂标识，
    同一根的两臂拿到逐字相同的赛程与牌山（配对红线）。焦点参赛者放在逻辑位
    focal_seat（table 1 的物理座位即 focal_seat；后续桌按合同 rotate_permutation
    轮换），其余逻辑位按合同 opponent_scenarios 顺序坐对手。
    """
    scenario = (contract["panel"]["opponent_scenarios"] or {}).get(str(opponent)) or {}
    opponent_policies = [str(name) for name in scenario.get("opponent_policies") or ()]
    if len(opponent_policies) != stage.SEAT_COUNT - 1:
        raise ValueError("合同对手情景 {0} 应有 {1} 家策略，得到 {2}".format(
            opponent, stage.SEAT_COUNT - 1, len(opponent_policies)))
    logical_participants: List[Dict[str, str]] = []
    opp_iter = iter(opponent_policies)
    for slot in range(stage.SEAT_COUNT):
        if slot == int(focal_seat):
            logical_participants.append({"participant_id": FOCAL_PARTICIPANT,
                                         "policy_name": "focal-arm"})
        else:
            logical_participants.append({"participant_id": "opp-{0}".format(slot),
                                         "policy_name": next(opp_iter)})
    root_seed = natural_root_seed(panel_seed, opponent, root_index)
    tables_per_group = int(contract["group"]["tables_per_group"])
    stage_spec = stage.ladder_stages(contract, stage.SEAT_COUNT)[0]
    plans = []
    for table_no in range(tables_per_group):
        table_id = natural_table_id(opponent, panel_seed, root_index,
                                    focal_seat, table_no + 1)
        plans.append(stage.build_table_plan(
            stage_no=1, stage_name=str(stage_spec["name"]), stage_role="qualify",
            stage_kind="group_round", table_id=table_id,
            participants=logical_participants,
            permutation=stage.rotate_permutation(table_no),
            seed=stage.derive_seed(root_seed, "table", table_id),
            tables_in_stage=tables_per_group, group_index=1))
    return plans


def arm_logical_policies(*, arm: str, candidate_scorer: Any,
                         logical_participants: Sequence[str],
                         opponent_policies: Sequence[str],
                         monotonic: Callable[[], float],
                         candidate_policy_factory: Optional[
                             Callable[[Callable[[], float]], Any]
                         ] = None) -> Dict[str, Any]:
    """按臂装配**逻辑位**策略：focal=候选/基线，其余=合同对手（两臂一致）。

    焦点逻辑位由计划给出（logical_participants 里的 FOCAL_PARTICIPANT；物理座位
    映射由 seat_policies_from 按 plan.permutation 统一完成）。focal 之外座位两臂
    策略完全一致：都走 sitin_stage.build_panel_policy 白名单装配（同源单一实现）；
    唯一差别是焦点逻辑位——候选臂默认是受限执行器装载的 ActionValuePolicy；
    新研究策略可显式注入 ``candidate_policy_factory(monotonic)``，仍由本函数按
    同一参赛者身份和物理座位装配。基线臂始终为 weighted_heuristic_v2。对手
    按 opponent_policies 顺序映射到非焦点逻辑位（与
    build_seat_stage_plans 的落位顺序一致）。
    """
    if arm not in ("baseline", "candidate"):
        raise ValueError("自然面板 arm 只能为 baseline 或 candidate：" + repr(arm))
    from hangma_bot.policy.action_value_policy import ActionValuePolicy

    policies: Dict[str, Any] = {}
    opp_iter = iter([stage.build_panel_policy(str(name), monotonic)
                     for name in opponent_policies])
    for participant in logical_participants:
        if participant == FOCAL_PARTICIPANT:
            if arm == "candidate" and candidate_policy_factory is not None:
                policies[participant] = candidate_policy_factory(monotonic)
            else:
                policies[participant] = (ActionValuePolicy(candidate_scorer)
                                         if arm == "candidate"
                                         else stage.build_panel_policy(
                                             BASELINE_FOCAL_POLICY, monotonic))
        else:
            policies[participant] = next(opp_iter)
    return policies


def execute_natural_table(*, plan: Any, policies_by_seat: Sequence[Any],
                          versions_block: Mapping[str, Any],
                          step_limit: int,
                          value_limits: ValueAnalysisLimits,
                          stage_situation: Optional[StageSituationProjection] = None
                          ) -> Dict[str, Any]:
    """在当前进程跑一个完整场次（与 sitin_stage.execute_table 同一执行方式）。

    差别只在策略来源：execute_table 按计划策略名解析（白名单/候选槽），本函数
    由调用方按臂注入已装配的 per-seat 策略对象；驱动、组合根运行时、时钟与
    结果组装（build_match_result）保持同构。value_limits 恒传（B3：action_value
    策略依赖 B1 分支进展/条件分值载荷）。

    stage_situation（M1）是该桌**开始前**已完成桌账的可见投影：非 None 时经
    drive_match 注入每个座位策略请求的 CompetitionContext（策略可见自己座位
    的阶段积分/名次分与剩余桌数）；None 保持旧空上下文（既有替身调用零变化）。
    """
    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy, ManualClock
    from hangma_bot.hangma.engine import HangmaRules

    rules_config = RuleConfig(ruleset_version=str(versions_block["ruleset_version"]),
                              base_score=int(versions_block["base_score"]),
                              you_cai_bi_kao=bool(versions_block["you_cai_bi_kao"]))
    timing = TimingConfig(**dict(stage.DEFAULT_TIMING))
    tournament_config = TournamentConfig(
        max_games=1, rounds_per_game=int(versions_block["rounds_per_game"]),
        rules=rules_config, timing=timing)
    runtime = getattr(bootstrap, BOOTSTRAP_RUNTIME_HOOK)("matches", MatchExperiment(
        kind="matches", clock_mode=str(versions_block["clock_mode"]),
        baseline=PolicyDeclaration(policy_id="natural-slot-a", name="panel", weights=()),
        challenger=PolicyDeclaration(policy_id="natural-slot-b", name="panel", weights=()),
        opponents=tuple(PolicyDeclaration(policy_id="natural-slot-{0}".format(index),
                                          name="panel", weights=())
                        for index in (3, 4, 5)),
        tournament_config=tournament_config,
        seeds=(MatchSeedSpec(seed=plan.seed, scenario_id=plan.scenario_id),),
        seat_permutations=(stage.IDENTITY_PERMUTATION,), initial_dealer=0,
        initial_scores=(0, 0, 0, 0)))
    if not isinstance(runtime, Mapping):
        raise RuntimeError("组合根未装配 matches 运行时；本工具不伪造模拟引擎")
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    now_monotonic = (clock.now if str(versions_block["clock_mode"]) == "logical"
                     else time.monotonic)
    rules = HangmaRules(rules_config)
    spec = runtime["spec_factory"](match_id=plan.match_id, scenario_id=plan.scenario_id,
                                   config=tournament_config, seed=plan.seed,
                                   initial_dealer=plan.initial_dealer,
                                   initial_scores=[0, 0, 0, 0])
    version_pairs = [
        ("clock_mode", str(versions_block["clock_mode"])),
        ("driver", "tools/sitin_natural_panel.py (offline.evaluate drive_match)"),
        ("panel_policy_names", sorted(set(str(name) for name in plan.policy_names))),
        ("rules_hash", compute_rules_hash(REPO)),
        ("ruleset_version", rules_config.ruleset_version),
        ("value_limits", json.dumps({"max_expansions": value_limits.max_expansions,
                                     "max_routes_per_candidate":
                                         value_limits.max_routes_per_candidate},
                                    sort_keys=True)),
    ]
    for seat, policy in enumerate(policies_by_seat):
        version_pairs.append(("natural_seat_policy:{0}".format(seat),
                              str(getattr(policy, "policy_id", type(policy).__name__))))
        if getattr(policy, "max_operations", None) is not None:
            version_pairs.append(("natural_seat_max_operations:{0}".format(seat),
                                  str(policy.max_operations)))
    started = time.monotonic()
    outcome = asyncio.run(drive_match(
        engine=runtime["engine"], spec=spec,
        policies_by_seat=tuple(policies_by_seat), rules=rules,
        choice_factory=runtime["choice_factory"],
        config=MatchDriverConfig(clock_mode=str(versions_block["clock_mode"]),
                                 step_limit=int(step_limit),
                                 budget_policy=BudgetPolicy(),
                                 competition_tournament_id=plan.scenario_id),
        now_monotonic=now_monotonic, wall_clock=None, value_limits=value_limits,
        stage_situation=stage_situation))
    wall_ms = (time.monotonic() - started) * 1000.0
    # 驱动fallbacks不包含所有策略内部降级；在逐窗口记录丢弃前独立计数。
    policy_execution = execution_audit.summarize(outcome.decisions,
        policy_ids_by_seat=[str(getattr(policy, "policy_id", type(policy).__name__))
                            for policy in policies_by_seat])
    version_pairs.extend([
        ("policy_execution_schema", execution_audit.SCHEMA),
        ("policy_execution_sha256", execution_audit.digest(policy_execution)),
    ])
    result = build_match_result(
        match_id=plan.match_id, scenario_id=plan.scenario_id, pair_id=plan.pair_id,
        config=tournament_config, policy_ids_by_seat=plan.seats(),
        seat_permutation=plan.permutation, initial_scores_physical=(0, 0, 0, 0),
        outcome=outcome, versions=tuple(sorted(version_pairs)),
        source_refs=({"note": "natural panel table",
                      "producer": "tools/sitin_natural_panel.py"},),
        result_id="r-" + plan.match_id, source_kind="simulation")
    return {
        "table_id": plan.table_id,
        "seed": int(plan.seed),
        "match_status": outcome.status,
        "wall_ms": round(wall_ms, 3),
        "scores_by_seat": (None if outcome.final_scores is None
                           else [int(item) for item in outcome.final_scores]),
        "result": result.to_json(),
        "policy_execution": policy_execution,
    }


def _execute_table_with_stage_account(**kwargs: Any) -> Dict[str, Any]:
    """调用桌执行入口，并在真实实现上传递阶段账投影（M1）。

    入口 execute_natural_table 是模块属性（测试可用桌执行替身替换）。既有
    0 桌结构测试的替身冻结了不含 stage_situation 的旧签名，因此这里按目标
    签名决定是否传递：声明了该参数（或 **kwargs）就传；否则按旧签名调用，
    不因新增参数被拒。**真实执行路径始终收到投影**（本模块实现声明了该参数），
    替身路径的注入由消费方另行核对（见 test_sitin_natural_panel.py）。
    """

    target = execute_natural_table
    try:
        parameters = inspect.signature(target).parameters
    except (TypeError, ValueError):  # 无签名可内省：按旧签名调用
        parameters = {}
    accepts = "stage_situation" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values())
    if not accepts:
        kwargs.pop("stage_situation", None)
    return target(**kwargs)


class ObservedDecisionPolicy:
    """离线诊断包装：观察原请求后原样调用策略；观察失败使该臂显式失败。"""

    def __init__(self, policy: Any, observer: Callable[[Any], None]) -> None:
        self.policy = policy
        self.observer = observer
        self.policy_id = getattr(policy, "policy_id", type(policy).__name__)
        self.max_operations = getattr(policy, "max_operations", None)
        self.error: Optional[Exception] = None

    async def choose(self, request: Any, budget: Any) -> Any:
        """观察器只接收合法可见请求，不接收模拟完整状态；不修改预算或返回计划。"""
        try:
            self.observer(request)
        except Exception as error:
            self.error = error
            raise
        return await self.policy.choose(request, budget)


def run_arm_stage(*, arm: str, plans: Sequence[Any], candidate_scorer: Any,
                  opponent_policies: Sequence[str], versions_block: Mapping[str, Any],
                  step_limit: int,
                  value_limits: ValueAnalysisLimits,
                  decision_observer: Optional[Callable[[Any], None]] = None,
                  candidate_policy_factory: Optional[
                      Callable[[Callable[[], float]], Any]
                  ] = None) -> Dict[str, Any]:
    """跑一臂的一个完整阶段实例（tables_per_group 桌）并求 group_advance_utility。

    每桌重新装配策略（与 execute_table 的 per-table 装配同构：候选评分器共享同一
    受限执行器实例，策略对象每桌新建）；**每桌开始前**按「参赛者身份 → 物理
    座位」注入已完成桌的阶段账（M1：积分/名次分/已完成与剩余赛程），当前桌
    结果单独维护、只在其结束后并入阶段账（不重复累计）；阶段终点账 = 各桌
    积分与名次分累计；U 识别区间调 sitin_stage.group_advance_utility（单一实现，
    缺 god_count 不补零）。decision_observer 仅用于离线采集焦点策略收到的
    DecisionRequest；默认不启用，其额外耗时不得用于线上时限验收。
    """
    if arm not in ("baseline", "candidate"):
        raise ValueError("自然面板 arm 只能为 baseline 或 candidate：" + repr(arm))
    from hangma_bot.application.deadline import ManualClock

    record: Dict[str, Any] = {"arm": arm, "status": None, "usable": False, "error": None,
                              "tables": [], "stage_totals_by_participant": None,
                              "focal_stage_score": None, "u": None, "u_low": None,
                              "u_high": None, "unresolved": None, "elapsed_ms": None}
    started = time.monotonic()
    totals: Dict[str, int] = {}
    place_totals: Dict[str, int] = {}
    rounds_per_game = int(versions_block["rounds_per_game"])
    try:
        for table_index, plan in enumerate(plans):
            # M1：本桌开始前注入**已完成桌**的阶段账（不含当前桌结果；桌内
            # 结果由驱动的 PlayerObservation.scores 单独维护，不重复累计）。
            situation = build_stage_situation(
                plan=plan, table_no=table_index + 1, tables_completed=table_index,
                totals=totals, place_totals=place_totals,
                rounds_per_game=rounds_per_game)
            clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
            logical = arm_logical_policies(arm=arm, candidate_scorer=candidate_scorer,
                                           logical_participants=plan.logical_participants,
                                           opponent_policies=opponent_policies,
                                           monotonic=clock.now,
                                           candidate_policy_factory=
                                               candidate_policy_factory)
            if decision_observer is not None:
                logical[FOCAL_PARTICIPANT] = ObservedDecisionPolicy(
                    logical[FOCAL_PARTICIPANT], decision_observer)
            policies_by_seat = seat_policies_from(
                logical, plan.permutation, plan.logical_participants)
            row = _execute_table_with_stage_account(
                plan=plan, policies_by_seat=policies_by_seat,
                versions_block=versions_block, step_limit=step_limit,
                value_limits=value_limits, stage_situation=situation)
            observed_policy = logical[FOCAL_PARTICIPANT]
            if decision_observer is not None and observed_policy.error is not None:
                raise RuntimeError("决策采集失败，诊断臂不可用") from observed_policy.error
            table_record = {key: row[key] for key in
                            ("table_id", "seed", "match_status", "wall_ms",
                             "scores_by_seat")}
            # 留存桌执行器实际返回的完整结果，供后续独立核验计划/完成单局数、
            # 座位映射、积分与运行计数。旧结构替身没有有效结果对象，仍只产摘要；
            # 不用空对象或摘要伪造完整结果。确认消费方必须严格拒绝缺失或坏结果。
            if row.get("result"):
                table_record["result"] = row["result"]
            if "policy_execution" in row:
                table_record["policy_execution"] = row["policy_execution"]
            # 证据留存：本桌策略实际收到的阶段账投影（可核，不冒充强度证据）。
            table_record["stage_situation"] = situation.to_json()
            record["tables"].append(table_record)
            if row.get("result"):
                execution_audit.verify_table(table_record)
            if row["match_status"] != "complete" or row["scores_by_seat"] is None:
                raise RuntimeError("场次 {0} 未完成（status={1}）".format(
                    plan.table_id, row["match_status"]))
            points = stage.place_points_for_table(row["scores_by_seat"])
            for seat, participant in enumerate(plan.seats()):
                totals[participant] = totals.get(participant, 0) + int(
                    row["scores_by_seat"][seat])
                place_totals[participant] = place_totals.get(participant, 0) + int(
                    points[seat])
        rows = [stage.LedgerRow(participant_id=pid, total_score=totals[pid],
                                place_points=place_totals[pid])
                for pid in sorted(totals)]
        utility = stage.group_advance_utility(rows, focal_id=FOCAL_PARTICIPANT)
        record.update({
            "status": "complete", "usable": True,
            "stage_totals_by_participant": dict(sorted(totals.items())),
            "stage_place_points_by_participant": dict(sorted(place_totals.items())),
            "focal_stage_score": int(totals[FOCAL_PARTICIPANT]),
            "u": (float(utility["u_low"] + utility["u_high"]) / 2.0
                  if utility["u_low"] == utility["u_high"] else None),
            "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
            "unresolved": utility["unresolved"],
            "u_interval": {"a": utility["a"], "b": utility["b"],
                           "tie_block": list(utility["tie_block"])},
        })
    except Exception as error:  # 臂级故障隔离（T16）：数值不冒充可用
        record["status"] = "error"
        record["error"] = "{0}: {1}".format(type(error).__name__, error)
    record["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 3)
    # 旧结构替身没有完整结果，仍按未知保留；不能生成零失败的伪证据。
    try:
        record["execution_review"] = execution_audit.review_tables(record["tables"], required=False)
    except ValueError as error:
        record["execution_review"] = {"status": "invalid", "error": str(error)}
        record["status"], record["usable"] = "error", False
        record["error"] = "评分执行审计不一致：" + str(error)
    return record


def _arm_sample_view(arm_record: Mapping[str, Any], *, candidate_id: str,
                     is_candidate: bool, baseline_id: str) -> Dict[str, Any]:
    """把一臂阶段记录转成 C2 样本臂结构（sitin_archive 可直接消费的形状）。"""
    return {
        "candidate_id": (candidate_id if is_candidate else baseline_id),
        "policy_id": ("action_value" if is_candidate else BASELINE_FOCAL_POLICY),
        "status": arm_record.get("status"),
        "usable": bool(arm_record.get("usable")),
        "error": arm_record.get("error"),
        "focal_stage_score": arm_record.get("focal_stage_score"),
        "stage_totals_by_participant": arm_record.get("stage_totals_by_participant"),
        "u": arm_record.get("u"),
        "u_low": arm_record.get("u_low"),
        "u_high": arm_record.get("u_high"),
        "unresolved": arm_record.get("unresolved"),
        "elapsed_ms": arm_record.get("elapsed_ms"),
    }


def run_natural_panel(*, candidate_source: str, opponent: str,
                      roots: Optional[int] = None,
                      seats_per_root: int, contract: Mapping[str, Any],
                      out_dir: Path, authorization: Mapping[str, Any],
                      panel_seed: int = DEFAULT_PANEL_SEED,
                      ledger_path: Optional[Path] = None,
                      ledger_authorized_budgets: Optional[Mapping[str, float]] = None,
                      min_roots: Optional[int] = None,
                      root_indices: Optional[Sequence[int]] = None,
                      root_seeds: Optional[Sequence[int]] = None,
                      execution_profile: Any = None,
                      admission: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """编排整个自然面板：根 × 焦点座位 × 双臂 → 样本 + 根级配对统计 + 费用账。

    Q3/Q4/Q7 纪律：--ledger 是真实执行入口的必需账本（CLI 强制）；授权额度
    未声明时正数记账 fail-closed；每样本带冻结期望清单 root_expected 与
    root_content_digest，任一臂失败/漏行/重复行使整根 invalid。

    **根选择（P2b）**：三种形式恰好给一个（roots=N 取前缀 / root_indices=[...] /
    root_seeds=[...]；口径与边界见 natural_root_selection）。根身份只由
    (对手, panel_seed, 根序号) 派生，故「按索引选根」与「按根数取前缀」对同一个根
    给出逐字节一致的 root_id/root_seed/table_id/root_content_digest——补根时只评
    参与者缺失的根即可，不必整前缀重跑（既有产物与账本步标识不变：前缀选择沿用
    旧记号；非前缀选择另有 idxN-M 记号，避免被前缀账行的结算挡住）。

    产物：out_dir/panel.json（config.roots = **选择集长度**；逐根 root_index 与
    source_root_id 在 samples 里可核）+ out_dir/samples.jsonl。不新增旁证文件：
    同一选择集（无论用哪种调用形式书写）产物逐字节一致，可 diff -r 对拍。
    """
    from hangma_bot.policy.action_value_seeds import ActionValueScorer

    require_authorization(authorization)
    declared_profile = execution_profiles.from_authorization(authorization)
    profile = execution_profiles.require_same(
        declared_profile, declared_profile if execution_profile is None else execution_profile)
    if profile["research_only"]:
        import sitin_gates
        if admission is None:
            raise ValueError("研究自然评测需要同源码同额度的受控研究准入记录")
        matched, why = sitin_gates.av_record_identity_matches(
            admission, candidate_source, execution_profile=profile)
        if not matched or admission.get("controlled_research_eligible") is not True:
            raise ValueError("研究自然评测准入未通过：" + why)
    if opponent not in ("H", "M"):
        raise ValueError("opponent 必须是 H/M 之一，得到 {0!r}".format(opponent))
    if not 1 <= int(seats_per_root) <= stage.SEAT_COUNT:
        raise ValueError("seats_per_root 必须在 1..{0}".format(stage.SEAT_COUNT))
    # P2b：根选择必须在任何副作用（建产物目录/预留费用/启动桌赛）之前解出并校验
    # ——非法根选择的拒绝必须早于一切执行与计费。
    selection = natural_root_selection(opponent=opponent, panel_seed=panel_seed,
                                       roots=roots, root_indices=root_indices,
                                       root_seeds=root_seeds)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenario = (contract["panel"]["opponent_scenarios"] or {})[str(opponent)]
    opponent_policies = [str(name) for name in scenario["opponent_policies"]]
    versions_block = stage.contract_versions_block(contract)
    value_limits = ValueAnalysisLimits()
    step_limit = int(contract["stop"]["step_limit"])
    tables_per_group = int(contract["group"]["tables_per_group"])
    av_contract_sha = hashlib.sha256((_project_file(_PROJECT_ROOT, REPO / AV_CONTRACT)).read_bytes()).hexdigest()
    scorer = ActionValueScorer("av-candidate", candidate_source,
                              max_operations=profile["max_operations"])
    candidate_id = scorer.candidate_identity(av_contract_sha)
    if profile["research_only"]:
        # 研究通道从第一步使用与准入/条件评测相同的强化身份，不事后改名。
        import sitin_gates
        candidate_id = sitin_gates.av_candidate_identity(candidate_source, execution_profile=profile)
    from sitin_search import ActionValueLedger, AV_BASELINE_ID

    ledger = None
    if ledger_path is not None:
        # Q3：统一必需账本——授权额度从参数或账本文件读取；两者皆无则正数
        # 记账 fail-closed（LedgerUnauthorized），不留无限额通道。
        ledger = ActionValueLedger.load(
            Path(ledger_path),
            authorized_budgets=dict(ledger_authorized_budgets)
            if ledger_authorized_budgets is not None else None)
    planned_tables = len(selection) * int(seats_per_root) * 2 * tables_per_group
    reservation = None
    if ledger is not None:
        # 步标识=根选择身份：前缀选择沿用旧记号（既有账行逐字不变），非前缀选择
        # 另有 idxN-M 记号——补根是不同任务，不能被前缀账行的结算挡死。
        selection_note = ("" if selection == tuple(range(1, len(selection) + 1))
                          else "；根索引 {0}".format(list(selection)))
        reservation = ledger.reserve(
            step_id="natural:{0}:{1}:{2}".format(
                candidate_id[:12], opponent, natural_selection_token(selection)),
            account="tables_full", amount=float(planned_tables),
            note="自然面板：{0} 根 × {1} 座位 × 2 臂 × {2} 桌/阶段{3}".format(
                len(selection), int(seats_per_root), tables_per_group,
                selection_note))
    wall_started = time.monotonic()
    cpu_started = time.process_time()

    seat_records: List[Dict[str, Any]] = []
    # 只评价**被选根**（升序规范序）：未选根不启动任何桌、不产生任何样本与费用。
    for root_index in selection:
        root_seed = natural_root_seed(panel_seed, opponent, root_index)
        root_id = natural_root_id(opponent, panel_seed, root_index)
        # Q4：任一臂（基线/候选）失败都收集——整根失效，不用剩余座位算选择值。
        root_arm_failures: List[str] = []
        root_seat_rows: Dict[int, Dict[str, Any]] = {}
        for focal_seat in range(int(seats_per_root)):
            plans = build_seat_stage_plans(contract=contract, opponent=opponent,
                                           root_index=root_index, focal_seat=focal_seat,
                                           panel_seed=panel_seed)
            arms = {
                "baseline": run_arm_stage(
                    arm="baseline", plans=plans, candidate_scorer=scorer,
                    opponent_policies=opponent_policies,
                    versions_block=versions_block, step_limit=step_limit,
                    value_limits=value_limits),
                "candidate": run_arm_stage(
                    arm="candidate", plans=plans, candidate_scorer=scorer,
                    opponent_policies=opponent_policies,
                    versions_block=versions_block, step_limit=step_limit,
                    value_limits=value_limits),
            }
            for arm_name, arm_record in arms.items():
                if not arm_record["usable"]:
                    root_arm_failures.append(
                        "seat{0}:{1}: {2}".format(focal_seat, arm_name,
                                                  arm_record["error"]))
                elif len(arm_record.get("tables") or ()) != tables_per_group:
                    # 漏行：臂未跑满冻结赛程（tables_per_group 桌）同样整根失效。
                    root_arm_failures.append(
                        "seat{0}:{1}: 赛程漏行（{2}/{3} 桌）".format(
                            focal_seat, arm_name,
                            len(arm_record.get("tables") or ()), tables_per_group))
            seat_records.append({
                "schema": NATURAL_SAMPLE_SCHEMA,
                "source_root_id": root_id,
                "candidate_id": candidate_id,
                "root_seed": root_seed,
                "root_index": root_index,
                "opponent_mix": opponent,
                "scenario": "normal",
                "focal_anchor_seat": focal_seat,
                # Q4：冻结期望双臂/座位/赛程清单（统计器按此整根校验）。
                "root_expected": {"seats": int(seats_per_root),
                                  "arms": ["baseline", "candidate"],
                                  "tables_per_arm": tables_per_group},
                "table_ids": [plan.table_id for plan in plans],
                "table_seeds": [int(plan.seed) for plan in plans],
                "seat_participants_by_table": [list(plan.seats()) for plan in plans],
                "arms": {
                    "baseline": _arm_sample_view(arms["baseline"],
                                                 candidate_id=candidate_id,
                                                 is_candidate=False,
                                                 baseline_id=AV_BASELINE_ID),
                    "candidate": _arm_sample_view(arms["candidate"],
                                                  candidate_id=candidate_id,
                                                  is_candidate=True,
                                                  baseline_id=AV_BASELINE_ID),
                },
                "raw_arms": arms,
                "completeness": "complete",
                "invalid_reasons": [],
                "cost": {"elapsed_ms": sum(float(arm.get("elapsed_ms") or 0.0)
                                           for arm in arms.values())},
            })
            root_seat_rows[int(focal_seat)] = seat_records[-1]
        # Q4：清单校验——座位缺行/重复行同样整根失效（fail-closed）。
        expected_seats = set(range(int(seats_per_root)))
        actual_seats = set(root_seat_rows)
        if actual_seats != expected_seats:
            root_arm_failures.append(
                "座位清单不符：缺 {0}，多余 {1}（期望 {2} 座位）".format(
                    sorted(expected_seats - actual_seats),
                    sorted(actual_seats - expected_seats), int(seats_per_root)))
        # Q7：根内容摘要——同 ID 不同内容的根由统计器拒绝（此处落档供核对）。
        root_digest = hashlib.sha256(json.dumps({
            "generator": NATURAL_PANEL_GENERATOR,
            "stage_projection": STAGE_ACCOUNT_MODE,
            "panel_seed": int(panel_seed), "opponent": opponent,
            "root_index": int(root_index), "root_seed": int(root_seed),
            "tables_per_arm": tables_per_group,
            "baseline_focal_policy": BASELINE_FOCAL_POLICY,
            "seats": {str(seat): {"table_ids": row["table_ids"],
                                  "table_seeds": row["table_seeds"]}
                      for seat, row in sorted(root_seat_rows.items())},
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        for row in root_seat_rows.values():
            row["root_content_digest"] = root_digest
        # T16 红线（Q4：两臂同权）：任一臂任一座位失败/漏行 ⇒ 整根标 invalid
        #（数值保留不冒充可用，费用照记；不删失败根继续选优）。
        if root_arm_failures:
            for record in seat_records:
                if record["root_index"] == root_index:
                    record["completeness"] = "invalid"
                    record["invalid_reasons"] = [
                        "臂执行失败/赛程漏行（T16 整根 invalid）：{0}".format(
                            "; ".join(root_arm_failures))]

    wall_sec = time.monotonic() - wall_started
    cpu_sec = time.process_time() - cpu_started
    effective_min_roots = (int(min_roots) if min_roots is not None
                           else min(2, len(selection)))
    statistics = paired_stage_statistics(seat_records, min_roots=effective_min_roots)
    # paired_stage_statistics 结构：by_candidate[cid].panels[scenario].panels[mix]。
    by_candidate = statistics.get("by_candidate") or {}
    candidate_block = by_candidate.get(candidate_id) or {}
    normal_block = (candidate_block.get("panels") or {}).get("normal", {})
    panels = normal_block.get("panels") or {}
    mix_panel = panels.get(str(opponent)) or {}

    if ledger is not None and reservation is not None:
        executed = sum(len((record.get("raw_arms") or {}).get("baseline", {})
                           .get("tables") or []) +
                       len((record.get("raw_arms") or {}).get("candidate", {})
                           .get("tables") or [])
                       for record in seat_records)
        ledger.settle(reservation, actual=float(executed),
                      note="自然面板实跑桌赛实例 {0}/{1}（失败桌照记）".format(
                          executed, planned_tables))
        ledger.save()
    contract_sha = hashlib.sha256(
        json.dumps(contract, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    try:
        execution_review = execution_audit.review_tables([
            table for sample in seat_records for arm in ("baseline", "candidate")
            for table in sample["raw_arms"][arm]["tables"]], required=False)
    except ValueError as error:
        # 坏审计的臂已标不可用；保留原始失败产物与费用，不能在写盘前丢失整批。
        execution_review = {"status": "invalid", "error": str(error)}
    panel = {
        "schema": NATURAL_PANEL_SCHEMA,
        "generator": NATURAL_PANEL_GENERATOR,
        "identity": {
            "candidate_id": candidate_id,
            "candidate_source_sha256": hashlib.sha256(
                candidate_source.encode("utf-8")).hexdigest(),
            "candidate_execution_profile": profile,
            "baseline_id": AV_BASELINE_ID,
            "contract_id": contract.get("contract_id"),
            "contract_sha256": contract_sha,
            "av_contract_sha256": av_contract_sha,
            "opponent_mix": opponent,
            "panel_seed": int(panel_seed),
            "panel_epoch": "{0}@{1}".format(NATURAL_PANEL_GENERATOR, opponent),
            "policy_execution_schema": execution_audit.SCHEMA,
            # M1：阶段信息投影方式（合同身份必需项 stage_projection）。
            "stage_projection": STAGE_ACCOUNT_MODE,
        },
        "config": {"roots": len(selection), "seats_per_root": int(seats_per_root),
                   "tables_per_group": tables_per_group,
                   "min_roots": effective_min_roots,
                   "opponent_policies": opponent_policies,
                   "focal_policy": {"baseline": BASELINE_FOCAL_POLICY,
                                    "candidate": "ActionValuePolicy(av-candidate)"},
                   "value_limits": {"max_expansions": value_limits.max_expansions,
                                    "max_routes_per_candidate":
                                        value_limits.max_routes_per_candidate},
                   "step_limit": step_limit},
        "samples": seat_records,
        "research_only": profile["research_only"],
        "automatic_archive_profile_supported": not profile["research_only"],
        "release_eligible": False,
        "execution_review": execution_review,
        "statistics": statistics,
        "cost": {
            "tokens_input": 0, "tokens_output": 0,
            "tables_full_planned": planned_tables,
            "tables_full_executed": sum(
                len(((record.get("raw_arms") or {}).get("baseline") or {})
                    .get("tables") or []) +
                len(((record.get("raw_arms") or {}).get("candidate") or {})
                    .get("tables") or [])
                for record in seat_records),
            "wall_sec": round(wall_sec, 3),
            "cpu_sec": round(cpu_sec, 3),
            "note": "tables_full 按每臂每座位每阶段 {0} 桌计；无 LLM 调用".format(
                tables_per_group),
        },
        "red_lines": {
            "stage_account_injection": (
                "每桌开始前按「参赛者身份 → 物理座位」注入已完成桌阶段账"
                "（不含当前桌；口径 {0}）".format(STAGE_ACCOUNT_MODE)),
            "non_focal_policies_identical_across_arms": True,
            "same_seed_both_arms": "table_id/seed 不含臂标识（同根同牌山）",
            "candidate_failure_policy": "T16：候选臂任一座位失败 ⇒ 整根 invalid，费用照记",
            "world_state_access": "仅经 drive_match 公开 PlayerObservation",
        },
    }
    write_json(out_dir / "panel.json", panel)
    with (out_dir / "samples.jsonl").open("w", encoding="utf-8") as handle:
        for record in seat_records:
            slim = {key: value for key, value in record.items() if key != "raw_arms"}
            handle.write(json.dumps(slim, ensure_ascii=False, sort_keys=True) + "\n")
    return panel


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="E 批次自然开局面板：正常阶段双臂配对评估（group-dev-v1 合同）")
    parser.add_argument("--candidate-source", required=True, help="候选源码文件")
    parser.add_argument("--opponent", required=True, choices=("H", "M"),
                        help="对手情景（合同 opponent_scenarios）")
    parser.add_argument("--roots", type=int, default=None,
                        help="根数（取前缀 1..N；与 --root-indices/--root-seeds "
                             "互斥；缺省 2）")
    parser.add_argument("--root-indices", default=None,
                        help="显式根索引列表（逗号分隔，如 3,4,5,6）：只评价这些根，"
                             "用于档案挑战补根（P2b；根身份与按根数取前缀一致）")
    parser.add_argument("--root-seeds", default=None,
                        help="显式根种子列表（逗号分隔）：每项必须能唯一回落到某根序号")
    parser.add_argument("--seats-per-root", type=int, default=4,
                        help="焦点座位轮换数（缺省 4；测试可收紧）")
    parser.add_argument("--contract-file", default=DEFAULT_CONTRACT,
                        help="阶段合同 JSON（缺省 group-dev-v1）")
    parser.add_argument("--out", required=True)
    parser.add_argument("--authorization", required=True,
                        help="批次 7 预算授权令牌 JSON（authorized=true 且 batch=7）")
    parser.add_argument("--admission", default=None,
                        help="研究额度必需：同源码同配置的action-value准入记录JSON")
    parser.add_argument("--panel-seed", type=int, default=DEFAULT_PANEL_SEED)
    parser.add_argument("--ledger", required=True,
                        help="必需账本 ActionValueLedger JSON 路径（Q3：真实执行"
                             "入口强制统一账本，无账本不启动任何桌赛）")
    parser.add_argument("--min-roots", type=int, default=None,
                        help="统计最少根数门槛（缺省 min(2, roots)）")
    args = parser.parse_args(argv)
    given = [name for name, value in (("--roots", args.roots),
                                      ("--root-indices", args.root_indices),
                                      ("--root-seeds", args.root_seeds))
             if value is not None]
    if len(given) > 1:
        parser.error("根选择参数互斥（恰好给一个）：{0}".format(given))

    def _csv_ints(raw: str) -> List[int]:
        return [int(chunk) for chunk in str(raw).replace(" ", "").split(",") if chunk]

    if args.root_indices is not None:
        selection_kwargs = {"root_indices": _csv_ints(args.root_indices)}
    elif args.root_seeds is not None:
        selection_kwargs = {"root_seeds": _csv_ints(args.root_seeds)}
    else:
        selection_kwargs = {"roots": 2 if args.roots is None else int(args.roots)}
    contract = json.loads(Path(args.contract_file).read_text(encoding="utf-8"))
    authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
    candidate_source = Path(args.candidate_source).read_text(encoding="utf-8")
    from sitin_search import av_ledger_budgets_from_authorization
    panel = run_natural_panel(
        candidate_source=candidate_source, opponent=args.opponent,
        seats_per_root=args.seats_per_root, contract=contract, out_dir=Path(args.out),
        authorization=authorization, panel_seed=args.panel_seed,
        ledger_path=Path(args.ledger),
        ledger_authorized_budgets=av_ledger_budgets_from_authorization(authorization),
        **({"admission": json.loads(Path(args.admission).read_text(encoding="utf-8"))}
           if args.admission else {}),
        min_roots=args.min_roots, **selection_kwargs)
    statistics = panel.get("statistics") or {}
    by_candidate = statistics.get("by_candidate") or {}
    mix = {}
    for block in by_candidate.values():
        mix = (((block.get("panels") or {}).get("normal") or {})
               .get("panels") or {}).get(args.opponent) or {}
        break
    # 自动监督器通常同时消费退出码与JSON；有样本对象不等于有可用结果。
    # 全无效、部分缺臂或根数不足都返回失败，避免只凭进程0误判完成。
    ok = (bool(panel["samples"]) and mix.get("status") == "ok"
          and all(s["completeness"] == "complete" for s in panel["samples"]))
    print(json.dumps({
        "ok": ok,
        "candidate_id": panel["identity"]["candidate_id"],
        "n_samples": len(panel["samples"]),
        "n_invalid": sum(1 for s in panel["samples"] if s["completeness"] != "complete"),
        "execution_review": panel.get("execution_review", {"status": "unknown"}),
        "tables_full": panel["cost"]["tables_full_executed"],
        "wall_sec": panel["cost"]["wall_sec"],
        "mean_delta": mix.get("mean_delta"),
        "interval_95": mix.get("interval_95"),
        "status": mix.get("status"),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
