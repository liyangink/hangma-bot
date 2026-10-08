"""既有等胡与七对续打的组合消融；研究装配，不新增自由赛枚举。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS,RISK_VERSION,SAFETY_MARGIN
from persistent_seven import PersistentSevenPolicy


def upgrade_policy():
    """使用主线冻结参数与逻辑时钟，未重新拟合条件世界的风险。"""
    return V2HuUpgradePolicy(monotonic=lambda:0,risk_cells=RISK_CELLS,
        risk_version=RISK_VERSION,safety_margin=SAFETY_MARGIN)


class UpgradePersistentPolicy:
    """有胡或已有爆头等待时交给原等胡实现，其余使用固定七对续打偏好。"""
    def __init__(self):
        self.upgrade=upgrade_policy()
        self.persistent=PersistentSevenPolicy(monotonic=lambda:0)

    async def choose(self,request,budget):
        """不让七对距离排序覆盖终点升级或保持爆头等待；只消费合法候选。"""
        if request.observation.rule_state.baotou or any(c.action_key=='hu' for c in request.rules.legal_candidates):
            return await self.upgrade.choose(request,budget)
        return await self.persistent.choose(request,budget)


class AuditedContinuation:
    """记录本人拒绝当前胡及改选次数，不把记录反馈给策略。"""
    def __init__(self,policy):
        self.policy=policy;self.hu_choices=[]

    async def choose(self,request,budget):
        plan=await self.policy.choose(request,budget)
        hu=next((c for c in request.rules.legal_candidates if c.action_key=='hu'),None)
        if hu is not None:
            obs=request.observation
            value=hu.value_facts
            settlement=None if value is None else value.immediate_settlement
            self.hu_choices.append(dict(seq=request.trigger_seq,action=plan.candidates[0].action_key,
                immediate_score=None if settlement is None else settlement.score_delta[obs.seat],
                details=None if settlement is None else settlement.details,
                hand=[t.code for t in obs.my_hand],draw=None if obs.drawn_tile is None else obs.drawn_tile.code,
                wall=obs.remaining_tile_count))
        return plan


class OwnValueFacts:
    """离线装配：本人分析使用生产可选价值事实，对手仍用原V2事实。"""
    def __init__(self,rules):self.rules=rules
    def analyze(self,observation):
        return self.rules.analyze(observation,value_limits=ValueAnalysisLimits() if observation.seat==0 else None)


class ValueEvaluationEngine:
    """为既有续打函数提供分析装配；完整世界仍只经模拟器公开方法传递。"""
    def __init__(self,engine):
        self.engine=engine;self.rules=OwnValueFacts(engine.rules)
    def frame(self,world):return self.engine.frame(world)
    def advance(self,world,revision,choices):return self.engine.advance(world,revision,choices)
    def export_hand(self,world,number):return self.engine.export_hand(world,number)
