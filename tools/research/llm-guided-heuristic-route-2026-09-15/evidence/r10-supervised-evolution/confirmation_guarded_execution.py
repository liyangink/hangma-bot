"""把已核验的依赖身份守卫接入可恢复双桌执行；不授予正式确认或发布资格。"""

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
from pathlib import Path
import confirmation_execution_identity as identity
import confirmation_execution_probe as execution

b=execution.b
SCHEMA='confirmation-guarded-execution/1'


def required_sources():
    """列出本执行接缝实际使用的实验辅助脚本；生产闭包由原身份构造器负责。"""
    modules=(identity,execution,execution.analysis,execution.pairing,
             execution.summary_verify,execution.full_verify,b)
    return {Path(__file__).resolve(),*(Path(module.__file__).resolve() for module in modules)}


def capture(*, entry_path, candidate_path, contract_path, additional_sources=()):
    """执行前冻结实际入口、候选、阶段合同及辅助脚本；写盘由调用方负责。

    entry_path须为实际调用本接缝的入口，additional_sources须包含入口另行导入的
    非生产辅助脚本。不能据此声称自动发现任意Python依赖或证明历史来源未曝光。
    """
    roles={name:str(Path(path).resolve()) for name,path in
           (('entry',entry_path),('candidate',candidate_path),('contract',contract_path))}
    sources=required_sources()|{Path(p) for p in roles.values()}|{Path(p).resolve() for p in additional_sources}
    return {'schema':SCHEMA,'source_roles':roles,
            'dependencies':identity.capture(source_paths=sources),'release_eligible':False}


def verify(frozen, *, root, expected):
    """预算预留前及执行/核验边界拒绝依赖、根、配置或候选字节身份不符。"""
    if frozen.get('schema')!=SCHEMA:
        raise ValueError('未知守卫执行身份版本')
    roles=frozen['source_roles'];dependencies=frozen['dependencies']
    if set(roles)!= {'entry','candidate','contract'}:
        raise ValueError('缺执行入口、候选或合同角色')
    mandatory=required_sources()|{Path(p).resolve() for p in roles.values()}
    if not {str(p) for p in mandatory} <= set(dependencies['explicit_sources']):
        raise ValueError('冻结身份缺必要执行源码')
    identity.verify(dependencies)
    identity.verify_root_runtime(root)
    if root['contract_digest']!=execution.analysis.digest(b.read(Path(roles['contract']))):
        raise ValueError('根计划不属于本次冻结阶段合同')
    if expected.get('execution_identity_digest')!=execution.analysis.digest(frozen):
        raise ValueError('执行请求未绑定本次守卫身份')
    if expected.get('root_content_digest')!=root['root_content_digest']:
        raise ValueError('执行请求根计划不符')
    if expected.get('candidate_source_sha256')!=dependencies['explicit_sources'][roles['candidate']]:
        raise ValueError('执行请求候选源码不符')
    matches=[cfg for cfg in root['configurations'] if execution.analysis.digest(cfg)==expected.get('plans_digest')]
    if len(matches)!=1 or expected.get('arm') not in ('baseline','candidate'):
        raise ValueError('执行请求配置或双臂身份不符')
    if type(expected.get('planned_tables')) is not int or expected['planned_tables']!=len(matches[0]['tables']):
        raise ValueError('执行请求桌数与计划不符')


def execute_arm(folder, *, frozen, root, expected, ledger, runner, verifier):
    """守卫后调用现有执行接缝，保留先预留、可恢复、不盲跑及保守计费语义。

    runner是真实模拟调用，verifier须核验完整MatchResult及阶段账；不能用测试替身
    证明算法效果。源码在执行中漂移时，已消耗费用保留，完整结果不获得通过标记。
    不支持敌手同时改写后还原文件的原子证明；正式运行仍需不可变工作区或进程隔离。
    """
    check=lambda:verify(frozen,root=root,expected=expected)
    check()
    def guarded_runner():
        check()
        return runner()
    def guarded_verifier(raw):
        check()
        result=verifier(raw)
        check()
        return result
    return execution.execute_arm(Path(folder),expected=expected,ledger=ledger,
                                 runner=guarded_runner,verifier=guarded_verifier)
