"""生成 3.1 的**格式夹具**（不是模型输出）。

用途：把"解析 → 静态扫描 → 隔离装载 → 血缘"这几段管线的正例/反例固定下来，
使 `--backend replay` 能在无网络、无凭据的机器上逐字节复现同一批结论。

**为什么夹具必须由脚本生成**：夹具里的 `prompt_sha256` 必须与当前提示词
逐字节一致（工具会校验，不符即拒绝）。合同或模板一改，旧夹具就会失效——
这是有意的 fail-closed；重跑本脚本即可重新对齐。

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation/make_fixtures.py

标注：所有夹具的 `origin` 都是 `format_fixture`，
工具会据此把它们标成 `is_model_output=false`、`admission.eligible=false`。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')

_spec = importlib.util.spec_from_file_location("sitin_generate", _project_file(_PROJECT_ROOT, TOOLS / "sitin_generate.py"))
gen = importlib.util.module_from_spec(_spec)
sys.modules["sitin_generate"] = gen
assert _spec.loader is not None
_spec.loader.exec_module(gen)

AUTHOR = "本会话 Agent（坐隐 3.1 包 genloop）"

#: I1 正例的机制说明与代码。
I1_THOUGHT = (
    "爆头态是总番 ×2 的状态，且是「飘」的前置条件；本方处于爆头时，"
    "普通弃牌会把爆头打掉，而打出财神（飘）不会。本机制在爆头态对一个"
    "普通弃牌候选追加固定负分，参数只有一个 penalty 与显式声明的最坏幅度 bound。"
)

I1_CODE = '''from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from hangma_bot.hangma.interface import CandidateFactKind, RuleCandidate
from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment

#: 夹具版本；改动语义必须同时改它（身份会随之变化）。
VERSION = "fixture-baotou-discard-guard-v1"


@dataclass(frozen=True)
class FixtureParams:
    """不可变参数实例；penalty 单位是评分点，bound 是最坏幅度上界。"""

    penalty: float = 8.0
    bound: float = 8.0
    scope: Tuple[str, ...] = ("discard",)

    def __post_init__(self) -> None:
        for name in ("penalty", "bound"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("FixtureParams.{0} 必须是有限数值".format(name))
        if self.penalty < 0 or self.bound <= 0:
            raise ValueError("penalty 必须非负、bound 必须为正")

    def to_json(self) -> str:
        return "penalty={0},bound={1}".format(self.penalty, self.bound)


def _discarded_tile(action_key: str) -> Optional[str]:
    """从动作键取被弃的牌值；非弃牌键返回空（**不猜**）。"""

    if ":" not in action_key:
        return None
    return action_key.split(":", 1)[1]


def _loses_baotou(candidate: RuleCandidate, ctx: EvaluationContext) -> bool:
    """该动作是否会把爆头打掉。

    只做**动作前状态**能支持的判断：爆头态下打出的若不是财神，就是普通弃牌。
    打出财神是「飘」，按官方规则保持爆头并延长动作链，因此不在此列。
    事实缺失或已胡一律退回 False（**不加不减，不猜**）。
    """

    facts = candidate.facts
    if facts is None:
        return False
    if facts.fact_kind is CandidateFactKind.WIN:
        return False
    tile = _discarded_tile(candidate.action_key)
    if tile is None:
        return False
    return tile != ctx.wealth_code


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """按声明参数构造候选；未知键直接报错，避免写错却静默用默认值。"""

    known = {"penalty", "bound"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("未知参数：{0}；可识别：{1}".format(sorted(unknown), sorted(known)))
    fixture = FixtureParams(**{key: float(params[key]) for key in known if key in params})

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidates
        if not ctx.baotou:
            return 0.0
        if not _loses_baotou(candidate, ctx):
            return 0.0
        return -fixture.penalty

    spec = AdjustmentSpec(
        name="夹具-爆头态弃牌保护",
        version=VERSION,
        thought=(
            "爆头是总番 ×2 的状态与「飘」的前置条件；爆头态下的普通弃牌会把它打掉，"
            "而打出财神（飘）不会。本项在爆头态对普通弃牌追加一个固定负分。"
            "这是一个**格式夹具**：它只用来验证生成管线，不声称任何效果。"),
        trigger=(
            "仅弃牌窗口；ctx.baotou 为真；被弃牌不是财神；facts 可用且非 WIN。"
            "非爆头态、打财神、事实缺失、已胡：一律返回 0.0（不加不减）"),
        scope=fixture.scope,
        bound=fixture.bound,
    )
    return HeuristicAdjustment(spec, delta,
                               source_fingerprint_value=source_fingerprint_value,
                               params_json=fixture.to_json())
'''

M1_THOUGHT = (
    "在父代基础上加一个手牌规模门控：手牌已经很小时爆头与番型都已无望，"
    "此时再为爆头扣分只会干扰牌效，因此只在手牌张数不少于 min_hand_tiles 时生效。"
)


def m1_code(parent_code: str) -> str:
    """M1 正例代码：父代 + 一处**有界**修订（新增手牌规模门控与参数）。"""

    revised = parent_code.replace(
        'VERSION = "fixture-baotou-discard-guard-v1"',
        'VERSION = "fixture-baotou-discard-guard-v2"')
    revised = revised.replace(
        '    penalty: float = 8.0\n    bound: float = 8.0\n'
        '    scope: Tuple[str, ...] = ("discard",)',
        '    penalty: float = 8.0\n    min_hand_tiles: float = 8.0\n'
        '    bound: float = 8.0\n    scope: Tuple[str, ...] = ("discard",)')
    revised = revised.replace(
        '        for name in ("penalty", "bound"):',
        '        for name in ("penalty", "min_hand_tiles", "bound"):')
    revised = revised.replace(
        '        return "penalty={0},bound={1}".format(self.penalty, self.bound)',
        '        return "penalty={0},min_hand_tiles={1},bound={2}".format(\n'
        '            self.penalty, self.min_hand_tiles, self.bound)')
    revised = revised.replace(
        '    known = {"penalty", "bound"}',
        '    known = {"penalty", "min_hand_tiles", "bound"}')
    revised = revised.replace(
        '        if not ctx.baotou:\n            return 0.0',
        '        if not ctx.baotou:\n            return 0.0\n'
        '        if len(ctx.combined_codes) < fixture.min_hand_tiles:\n'
        '            return 0.0')
    return revised


#: 修复型 M1 的机制说明与代码：父代越界 import 被拒，改成显式声明参数。
REPAIR_THOUGHT = (
    "按拒绝诊断修订：父代读取环境变量（越界 import），改为把权重作为**声明参数**"
    "从外部传入，模块内不再有任何环境或文件访问；其余机制保持不变。"
)

REPAIR_CODE = '''from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Tuple

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment

#: 修复型夹具版本。
VERSION = "fixture-repaired-weight-v1"


@dataclass(frozen=True)
class RepairParams:
    """不可变参数实例：weight 由声明参数给出（不再读环境）。"""

    weight: float = 1.0
    bound: float = 10.0
    scope: Tuple[str, ...] = ("discard",)

    def __post_init__(self) -> None:
        if type(self.weight) not in (int, float) or not math.isfinite(self.weight):
            raise ValueError("RepairParams.weight 必须是有限数值")
        if self.bound <= 0:
            raise ValueError("RepairParams.bound 必须为正")

    def to_json(self) -> str:
        return "weight={0},bound={1}".format(self.weight, self.bound)


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """按声明参数构造候选；未知键直接报错。"""

    known = {"weight", "bound"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("未知参数：{0}".format(sorted(unknown)))
    repair = RepairParams(**{key: float(params[key]) for key in known if key in params})

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidate, ctx, candidates
        return repair.weight

    spec = AdjustmentSpec(
        name="夹具-修复型权重", version=VERSION,
        thought="修复型夹具：把越界的环境读取换成声明参数。",
        trigger="恒触发（夹具）。", scope=repair.scope, bound=repair.bound)
    return HeuristicAdjustment(spec, delta, source_fingerprint_value=source_fingerprint_value,
                               params_json=repair.to_json())
'''

#: 反例 1：没有花括号内的机制说明（代码本身合法，只有格式不合规）。
NEG_MISSING_THOUGHT = "先说结论：我改了一个弃牌分支。\n\n" + gen.FENCE + "python\n" + I1_CODE + gen.FENCE + "\n"

#: 反例 2：静态扫描必须拦下的 import（os 不在白名单，也是文件/系统副作用入口）。
NEG_FORBIDDEN_IMPORT_CODE = '''from __future__ import annotations

import os
from typing import Mapping

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """反例夹具：读取环境变量决定分值——静态扫描必须拒绝。"""

    weight = float(os.environ.get("SITIN_FIXTURE_WEIGHT", "1"))

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidate, ctx, candidates
        return weight

    spec = AdjustmentSpec(name="夹具-越界 import", version="fixture-forbidden-import-v1",
                          thought="反例夹具：只用于验证拒绝路径。",
                          trigger="恒触发。", scope=("discard",), bound=10.0)
    return HeuristicAdjustment(spec, delta)
'''

NEG_FORBIDDEN_IMPORT = "{说明：读环境变量改评分。}\n\n" + gen.FENCE + "python\n" + NEG_FORBIDDEN_IMPORT_CODE + gen.FENCE + "\n"

#: 反例 3：模块体死循环；解析与静态扫描都会通过，**必须**由受监管装载拦住。
NEG_INFINITE_LOOP = '''{加载期死循环探针：用来验证隔离装载会被墙钟上限终止。}

@@FENCE@@python
from __future__ import annotations

from typing import Mapping

from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment
from hangma_bot.hangma.interface import RuleCandidate

while True:
    pass


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """永远到不了这里；夹具只用于验证装载阶段的可终止性。"""

    raise NotImplementedError
@@FENCE@@
'''


def _reply(thought: str, code: str) -> str:
    """按 EoH 统一格式拼一条回复：**花括号内的**一句话 + 唯一一个 python 围栏代码块。

    注意花括号是格式的一部分：初版漏了它，而当时的解析器在全文里找第一个 {...}，
    于是从代码里的 "{0}" 捡了一个"说明"回来，把一条不合格式的回复判成了 ok。
    解析器修好之后这条夹具立刻被正确拒绝——两处都不是"看起来能用"就该放过。
    """

    return ("{" + thought + "}\n\n" + gen.FENCE + "python\n"
            + code.rstrip("\n") + "\n" + gen.FENCE + "\n")


def _fixture(*, origin: str, prompt_sha: str, reply: str, **extra) -> dict:
    payload = {"schema": gen.REPLY_FILE_SCHEMA, "origin": origin,
               "prompt_sha256": prompt_sha, "reply": reply}
    payload.update(extra)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 3.1 格式夹具")
    parser.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, _HERE / "fixtures")))
    parser.add_argument("--parent", default=None,
                        help="M1 夹具的父代尝试目录（含 record.json）")
    parser.add_argument("--feedback", default=None, help="M1 夹具的反馈文本文件")
    parser.add_argument("--repair-parent", default=None,
                        help="修复型 M1 夹具的父代目录（自身装载失败，靠拒绝诊断修订）")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    contract = gen.default_task_contract()
    prompt = gen.build_i1_prompt(contract)
    written = []

    fixtures = {
        "i1-positive.json": _fixture(
            origin=gen.ORIGIN_FIXTURE, prompt_sha=prompt.sha256,
            reply=_reply(I1_THOUGHT, I1_CODE), author=AUTHOR,
            purpose="I1 正例：验证 解析→静态扫描→隔离装载→血缘 全链路"),
        "i1-negative-missing-thought.json": _fixture(
            origin=gen.ORIGIN_FIXTURE, prompt_sha=prompt.sha256,
            reply=NEG_MISSING_THOUGHT, author=AUTHOR,
            purpose="反例：缺少花括号内的机制说明，解析必须拒绝"),
        "i1-negative-forbidden-import.json": _fixture(
            origin=gen.ORIGIN_FIXTURE, prompt_sha=prompt.sha256,
            reply=NEG_FORBIDDEN_IMPORT, author=AUTHOR,
            purpose="反例：白名单外 import，静态扫描必须拒绝"),
        "i1-negative-infinite-loop.json": _fixture(
            origin=gen.ORIGIN_FIXTURE, prompt_sha=prompt.sha256,
            reply=NEG_INFINITE_LOOP.replace("@@FENCE@@", gen.FENCE), author=AUTHOR,
            purpose="反例：模块体死循环，隔离装载必须由墙钟上限终止（用 --load-timeout-sec 3）"),
    }
    for name, payload in fixtures.items():
        (out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        written.append(name)

    if args.repair_parent:
        # 修复型 M1：父代**装载失败**（例如越界 import），提示词里带拒绝诊断。
        repair_dir = Path(args.repair_parent)
        repair_parent = gen.parent_binding(repair_dir)
        diagnosis = json.loads((repair_dir / "record.json").read_text(encoding="utf-8"))
        repair_feedback = gen.feedback_from_diagnosis(diagnosis)
        repair_prompt = gen.build_m1_prompt(
            contract, repair_parent["thought"], repair_parent["code"], repair_feedback,
            parent_identity=repair_parent["identity"])
        payload = _fixture(
            origin=gen.ORIGIN_FIXTURE, prompt_sha=repair_prompt.sha256,
            reply=_reply(REPAIR_THOUGHT, REPAIR_CODE), author=AUTHOR,
            purpose="修复型 M1：父代装载失败（越界 import），按拒绝诊断去掉越界访问")
        (out / "m1-repair-positive.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append("m1-repair-positive.json")

    if args.parent:
        parent = gen.parent_binding(Path(args.parent))
        feedback = (Path(args.feedback).read_text(encoding="utf-8")
                    if args.feedback else "（无反馈：仅验证格式与血缘）")
        m1_prompt = gen.build_m1_prompt(contract, parent["thought"], parent["code"], feedback,
                                        parent_identity=parent["identity"])
        payload = _fixture(
            origin=gen.ORIGIN_FIXTURE, prompt_sha=m1_prompt.sha256,
            reply=_reply(M1_THOUGHT, m1_code(parent["code"])), author=AUTHOR,
            purpose="M1 正例：父代 + 一处有界修订（手牌规模门控），验证血缘绑定父代身份")
        (out / "m1-positive.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append("m1-positive.json")

    print(json.dumps({"written": written, "out": str(out),
                      "i1_prompt_sha256": prompt.sha256}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
