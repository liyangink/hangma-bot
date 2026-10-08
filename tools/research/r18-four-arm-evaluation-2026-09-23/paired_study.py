"""四策略同牌山换座完整桌赛；按对手组合×牌山根保留独立统计单位。

本工具只调用现有自然面板和生产策略，不实现第二套规则或观察编码。
默认小批为 H/M 各 2 根，用于检查运行与估计速度；正式确认必须换新的
panel_seed，且在执行前冻结根数与判据（见同目录 PLAN.md）。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for entry in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools")):
    sys.path.insert(0, str(entry))

import sitin_natural_panel as natural  # noqa: E402
from hangma_bot.bootstrap import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.offline.evaluation_results import compute_rules_hash  # noqa: E402
from hangma_bot.hangma import value_analysis  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v1_release import (  # noqa: E402
    R18IntegratedPositiveV1ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
)
from hangma_bot.policy.r18_integrated_positive_v2_release import (  # noqa: E402
    R18IntegratedPositiveV2ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
)
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy  # noqa: E402

CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
ARMS = ("weighted_heuristic_v2", "v2_hu_upgrade_v1", "r18_v1", "r18_v2")
# 序列策略网络臂：sequence@<部署包目录名> 装载 prebuilt/sequence-policy-models/<名>。
# 2026-09-25 新增：仓库里三个已训练网络在开发面板上对 V2 的点估计为正
# （+1.28 到 +3.33 分/桌）但八项主要区间全部跨零，且从未与 R18 v2 直接比较过。
# 这个臂让两者第一次进同一牌山换座设计。模型规则配置不符时装载即失败，不静默降级。
SEQUENCE_ARM_PREFIX = "sequence@"
SEQUENCE_MODEL_ROOT = _project_file(_PROJECT_ROOT, ROOT / "prebuilt" / "sequence-policy-models")
# 诊断臂：与 sequence@ 同构，但把每次决策的 degraded_reasons 追加到
# <out>/degraded-reasons.jsonl。用于回答「网络到底有没有被使用」——
# 三个不同 checkpoint 给出逐点相同的分数时，必须分清是模型无效还是接线降级。
SEQUENCE_DEBUG_PREFIX = "sequence_debug@"
_DEGRADED_SINK = None
# 研究种子臂：seed@<种子名> 装载 action_value 的静态种子策略
# （efficiency_seed / route_value_seed / hu_first_reference）。
# 2026-09-25 新增：这三个种子是仓库里**已注册、可从 bootstrap 装配、
# 却从未与冻结父代直接比较过**的候选策略；route_value_seed 用的比较量
# （family_progress + 有界结算因子）与父代的进张求和不是同一个。
SEED_ARM_PREFIX = "seed@"
# 自定义臂：`candidate@<相对仓库根的源码路径>` 把该文件内容当作与发布候选同形的
# 源码字符串装载。消融实验（EVOLUTION.md P3）用它把"只改一个常数的候选"作为一条臂
# 传进来，**不新增也不改动任何已注册发布身份**。首个臂始终是差值基准。
CANDIDATE_ARM_PREFIX = "candidate@"
MIXES = ("H", "M")
SEATS = (0, 1, 2, 3)
LIMITS = ValueAnalysisLimits()


def digest(path: Path) -> str:
    """计算执行输入文件的 SHA-256，供恢复运行时拒绝漂移。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_identity() -> dict[str, str]:
    """冻结当前策略与自然面板的实际源码身份。"""
    relative = (
        'tools/research/r18-four-arm-evaluation-2026-09-23/paired_study.py',
        'tools/offline/sitin/sitin_natural_panel.py',
        "review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json",
        "src/hangma_bot/policy/heuristic_v2.py",
        "src/hangma_bot/policy/v2_hu_upgrade.py",
        "src/hangma_bot/policy/r18_integrated_positive_v1.py",
        "src/hangma_bot/policy/r18_integrated_positive_v2.py",
        "src/hangma_bot/policy/action_value.py",
        "src/hangma_bot/hangma/value_analysis.py",
    )
    return {item: digest(_project_file(_PROJECT_ROOT, ROOT / item)) for item in relative}


def parse_arms(spec: str | None) -> tuple[str, ...]:
    """解析 `--arms`；缺省时返回与历史完全相同的四臂，旧运行仍可恢复。"""

    if spec is None:
        return ARMS
    arms = tuple(item.strip() for item in spec.split(",") if item.strip())
    if len(arms) < 2:
        raise SystemExit("--arms 至少需要两个臂（首个为差值基准）")
    if len(set(arms)) != len(arms):
        raise SystemExit("--arms 不允许重复臂名")
    for arm in arms:
        if arm.startswith(CANDIDATE_ARM_PREFIX):
            if not (_project_file(_PROJECT_ROOT, ROOT / arm[len(CANDIDATE_ARM_PREFIX):])).is_file():
                raise SystemExit("研究候选源码不存在：" + arm[len(CANDIDATE_ARM_PREFIX):])
        elif arm.startswith(SEED_ARM_PREFIX):
            from hangma_bot.policy.action_value_seeds import SEED_NAMES
            if arm[len(SEED_ARM_PREFIX):] not in SEED_NAMES:
                raise SystemExit("未知种子名：" + arm)
        elif arm.startswith(SEQUENCE_ARM_PREFIX) or arm.startswith(SEQUENCE_DEBUG_PREFIX):
            prefix = (SEQUENCE_DEBUG_PREFIX if arm.startswith(SEQUENCE_DEBUG_PREFIX)
                      else SEQUENCE_ARM_PREFIX)
            directory = _project_file(_PROJECT_ROOT, SEQUENCE_MODEL_ROOT / arm[len(prefix):])
            if not (directory / "manifest.json").is_file():
                raise SystemExit("序列策略部署包不存在：" + str(directory))
        elif arm not in ARMS:
            raise SystemExit("未知策略臂（可用 %s 或 candidate@<路径>）：%s"
                             % (", ".join(ARMS), arm))
    return arms


def candidate_sources(arms: tuple[str, ...]) -> dict[str, str]:
    """研究候选臂的源码摘要；写进清单使恢复运行能发现候选文件被改。"""

    return {arm: digest(_project_file(_PROJECT_ROOT, ROOT / arm[len(CANDIDATE_ARM_PREFIX):]))
            for arm in arms if arm.startswith(CANDIDATE_ARM_PREFIX)}


class _DegradedRecorder:
    """只读包装：转发 choose，并把降级原因追加到诊断文件。不改变任何行为。"""

    def __init__(self, inner):
        self._inner = inner
        self.policy_id = getattr(inner, "policy_id", type(inner).__name__)

    async def choose(self, request, budget):
        plan = await self._inner.choose(request, budget)
        reasons = tuple(getattr(plan, "degraded_reasons", ()) or ())
        import os
        sink = os.environ.get("PAIRED_STUDY_DEGRADED_SINK")
        if sink:
            candidates = tuple(getattr(plan, "candidates", ()) or ())
            top = candidates[0].action_key if candidates else None
            top_score = candidates[0].total_score if candidates else None
            line = json.dumps({"reasons": list(reasons), "top": top,
                               "top_score": top_score,
                               "n": len(candidates)}) + "\n"
            fd = os.open(sink, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
        return plan


def policy_factory(arm: str):
    """按真实策略身份构造焦点策略；他家由冻结自然面板装配。"""
    rules_hash = compute_rules_hash(ROOT)
    analysis_hash = digest(Path(value_analysis.__file__))

    def build(monotonic):
        if arm == "weighted_heuristic_v2":
            return ComparableHeuristicPolicyV2(monotonic=monotonic)
        if arm == "v2_hu_upgrade_v1":
            return V2HuUpgradePolicy(
                monotonic=monotonic,
                risk_cells=RISK_CELLS,
                risk_version=RISK_VERSION,
                safety_margin=SAFETY_MARGIN,
            )
        if arm == "r18_v1":
            return R18IntegratedPositiveV1ReleasePolicy(
                rules_source_hash=rules_hash,
                value_analysis_sha256=analysis_hash,
            )
        if arm == "r18_v2":
            return R18IntegratedPositiveV2ReleasePolicy(
                rules_source_hash=rules_hash,
                value_analysis_sha256=analysis_hash,
            )
        if arm.startswith(SEED_ARM_PREFIX):
            # 研究种子：静态注册的受限执行器候选，与发布父代同形。
            return ActionValuePolicy.from_seed(arm[len(SEED_ARM_PREFIX):],
                                               value_limits=ValueAnalysisLimits())
        if arm.startswith(SEQUENCE_ARM_PREFIX) or arm.startswith(SEQUENCE_DEBUG_PREFIX):
            # 序列策略网络：网络对全部合法候选独立评分并重写排序，
            # 基线只提供保底、覆盖校验与降级路径（见 training-direction 复核 C-3）。
            from dataclasses import asdict

            from hangma_bot.bootstrap import DEFAULT_RULESET_VERSION
            from hangma_bot.kernel.config import RuleConfig
            from hangma_bot.learning.sequence_model_artifact import load_sequence_model
            from hangma_bot.policy.safe_fallback import SafeFallbackPolicy
            from hangma_bot.policy.sequence_model_policy import SequenceModelPolicy

            prefix = (SEQUENCE_DEBUG_PREFIX if arm.startswith(SEQUENCE_DEBUG_PREFIX)
                      else SEQUENCE_ARM_PREFIX)
            directory = _project_file(_PROJECT_ROOT, SEQUENCE_MODEL_ROOT / arm[len(prefix):])
            network, artifact = load_sequence_model(directory)
            runtime_rules = RuleConfig(DEFAULT_RULESET_VERSION, 1, False)
            if asdict(runtime_rules) != artifact.rule_config:
                raise SystemExit("序列策略制品声明的规则配置与本机运行规则不一致：" + arm)
            # baseline 必须与本臂共用同一个单调时钟：面板传的是逻辑时钟
            # （ManualClock 起始 800.0），而预算也按该时钟构造。若这里漏传
            # monotonic，基线会拿真实 time.monotonic 去比逻辑截止，
            # 每次都抛 baseline_error，SequenceModelPolicy 于是全程返回
            # **紧急保底**（n=1、score=1.0）。2026-09-25 的 P9 因此白跑一批：
            # 三个不同 checkpoint 给出逐点相同且极差的分数。
            policy = SequenceModelPolicy(
                baseline=V2HuUpgradePolicy(monotonic=monotonic, risk_cells=RISK_CELLS,
                                           risk_version=RISK_VERSION,
                                           safety_margin=SAFETY_MARGIN),
                fallback=SafeFallbackPolicy(), network=network, artifact=artifact,
                runtime_rules=runtime_rules, monotonic=monotonic,
            )
            if prefix == SEQUENCE_DEBUG_PREFIX:
                return _DegradedRecorder(policy)
            return policy
        if arm.startswith(CANDIDATE_ARM_PREFIX):
            # 研究候选：只装载源码文本，不绑定发布包身份，也不改变其余臂。
            path = _project_file(_PROJECT_ROOT, ROOT / arm[len(CANDIDATE_ARM_PREFIX):])
            source = path.read_text(encoding="utf-8")
            return ActionValuePolicy(
                ActionValueScorer("research:" + path.stem, source),
                value_limits=ValueAnalysisLimits(),
            )
        raise ValueError("未知策略臂：" + arm)

    return build


def run_unit(unit: tuple[str, int, int, str, int]) -> dict[str, Any]:
    """执行一个对手组合、牌山根、焦点座位与策略臂的完整阶段。"""
    mix, root_index, seat, arm, panel_seed = unit
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=mix,
        root_index=root_index,
        focal_seat=seat,
        panel_seed=panel_seed,
    )
    stage = natural.run_arm_stage(
        arm="candidate",
        plans=plans,
        candidate_scorer=None,
        candidate_policy_factory=policy_factory(arm),
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
    )
    return {"mix": mix, "root_index": root_index, "focal_seat": seat,
            "arm": arm, "stage": stage}


def write_json(path: Path, data: Any) -> None:
    """以 UTF-8 原子写入一个阶段或运行清单，避免中断时留下半行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                    indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def safe_arm_name(arm: str) -> str:
    """把臂名转成文件名安全片段。

    研究候选臂的名字形如 `candidate@review/…/OPTY-R18-C03-RIVER0.py`，含路径分隔符。
    直接拼进文件名会把阶段文件写进嵌套子目录（功能上能跑，但路径脆弱、可读性差）。
    这里只做文件名安全化，**不改动臂名本身**——臂名仍是清单与汇总里的身份键。
    """

    return re.sub(r"[^A-Za-z0-9_.@-]+", "_", arm)


def unit_path(out: Path, unit: tuple[str, int, int, str, int]) -> Path:
    """返回阶段文件路径；路径不依赖策略执行结果。

    注意：本函数在 2026-09-25 引入文件名安全化，路径相比此前的研究候选批次会变化。
    已完成的批次不受影响（只是不再被识别为"已完成"而重新计算），已注册臂名不含
    特殊字符，路径与历史完全一致。
    """

    mix, root_index, seat, arm, _seed = unit
    return out / "stages" / f"{mix}-r{root_index:04d}-s{seat}-{safe_arm_name(arm)}.json"


def main() -> None:
    """冻结输入后运行或恢复；任何阶段失败都会阻止效果汇总。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--panel-seed", type=int, default=2026102311)
    parser.add_argument("--root-start", type=int, default=1)
    parser.add_argument("--roots-per-mix", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--arms", default=None,
                        help="逗号分隔的臂名，首个为差值基准；默认沿用历史四臂。"
                             "研究候选写 candidate@<相对仓库根的源码路径>")
    args = parser.parse_args()
    if args.root_start < 1 or args.roots_per_mix < 1 or not 1 <= args.workers <= 8:
        parser.error("根起点/根数必须为正，工作进程必须在 1..8")
    if args.root_start + args.roots_per_mix - 1 > natural.MAX_ROOT_INDEX:
        parser.error("自然面板的根序号不得超过 99")
    arms = parse_arms(args.arms)
    # 诊断输出走环境变量：ProcessPoolExecutor 在 macOS 用 spawn，模块级全局不会
    # 传到工作进程，2026-09-25 因此白跑过一次诊断（文件根本没被创建）。
    if any(a.startswith(SEQUENCE_DEBUG_PREFIX) for a in arms):
        os.environ["PAIRED_STUDY_DEGRADED_SINK"] = str(args.out / "degraded-reasons.jsonl")
    units = [
        (mix, root_index, seat, arm, args.panel_seed)
        for mix in MIXES
        for root_index in range(args.root_start, args.root_start + args.roots_per_mix)
        for seat in SEATS
        for arm in arms
    ]
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    manifest = {
        "schema": "r18-four-arm-paired-study/1",
        "panel_seed": args.panel_seed,
        "root_start": args.root_start,
        "roots_per_mix": args.roots_per_mix,
        "mixes": list(MIXES),
        "seats": list(SEATS),
        "arms": list(arms),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "planned_complete_tables": len(units) * int(contract["group"]["tables_per_group"]),
        "statistical_unit": "opponent_mix×root_index；四座位先在根内平均",
        "rules_source_hash": compute_rules_hash(ROOT),
        "r18_v1_release_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        "r18_v2_release_id": R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        "input_identity": input_identity(),
    }
    # 仅在存在研究候选臂时增加该键：否则清单形状与历史运行完全一致，旧运行仍可恢复。
    sources = candidate_sources(arms)
    if sources:
        manifest["candidate_sources"] = sources
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise SystemExit("现有运行清单与本次输入不同，拒绝混合或覆盖")
    else:
        write_json(manifest_path, manifest)
    pending = []
    for unit in units:
        path = unit_path(args.out, unit)
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if row["stage"]["status"] != "complete" or len(row["stage"]["tables"]) != manifest["tables_per_stage"]:
                raise SystemExit("已有阶段不完整：" + str(path))
        else:
            pending.append(unit)
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_unit, unit): unit for unit in pending}
            for future in concurrent.futures.as_completed(futures):
                unit = futures[future]
                row = future.result()
                write_json(unit_path(args.out, unit), row)
                if row["stage"]["status"] != "complete":
                    raise RuntimeError("阶段失败，已保留证据：" + str(unit_path(args.out, unit)))
    scores: dict[tuple[str, int, str], list[int]] = {}
    for unit in units:
        row = json.loads(unit_path(args.out, unit).read_text(encoding="utf-8"))
        score = row["stage"].get("focal_stage_score")
        if row["stage"]["status"] != "complete" or type(score) is not int:
            raise RuntimeError("阶段积分缺失：" + str(unit_path(args.out, unit)))
        scores.setdefault((unit[0], unit[1], unit[3]), []).append(score)
    roots = []
    tables_per_stage = manifest["tables_per_stage"]
    for mix in MIXES:
        for root_index in range(args.root_start, args.root_start + args.roots_per_mix):
            stage_means = {arm: sum(scores[(mix, root_index, arm)]) / len(SEATS) for arm in arms}
            table_means = {arm: stage_means[arm] / tables_per_stage for arm in arms}
            row = {"mix": mix, "root_index": root_index,
                   "stage_score_mean_by_arm": stage_means,
                   "table_score_mean_by_arm": table_means,
                   "delta_vs_baseline_per_table": {
                       arm: table_means[arm] - table_means[arms[0]] for arm in arms[1:]},
                   # 兼容键：只有默认四臂都到场时才给 R18 v2 对 v1 的差值。
                   "delta_vs_v2_per_table": {
                       arm: table_means[arm] - table_means[arms[0]] for arm in arms[1:]}}
            if "r18_v2" in table_means and "r18_v1" in table_means:
                row["delta_r18_v2_vs_v1_per_table"] = table_means["r18_v2"] - table_means["r18_v1"]
            roots.append(row)
    write_json(args.out / "result.json", {
        "schema": "r18-four-arm-paired-result/1",
        "complete_tables": manifest["planned_complete_tables"],
        "independent_root_clusters": len(roots),
        "root_clusters": roots,
        "baseline_arm": arms[0],
        "descriptive_mean_delta_vs_baseline_per_table": {
            arm: sum(row["delta_vs_baseline_per_table"][arm] for row in roots) / len(roots)
            for arm in arms[1:]
        },
        "descriptive_mean_delta_vs_v2_per_table": {
            arm: sum(row["delta_vs_v2_per_table"][arm] for row in roots) / len(roots)
            for arm in arms[1:]
        },
        "note": "小批均值只校验执行与估计方差；正式结论使用独立根、预冻结多重比较门禁。"
                " delta_vs_v2_per_table 的名称是历史遗留，基准实为 arms[0]。",
    })
    print(f"{len(roots)} 个独立牌山根、{manifest['planned_complete_tables']} 桌完成：{args.out / 'result.json'}")


if __name__ == "__main__":
    main()
