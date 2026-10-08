"""原生机械函数下执行公共规则回归，记录真实规则/fixture评分调用与完整输入。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t124-native-mechanical-functions-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parent
RUNTIME=Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0]=[str(RUNTIME),str(_project_file(_PROJECT_ROOT, RUNTIME/'src'))]
from mechanical_overlay import installed
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture,ScoringInputCaptureLimits
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.simulation.engine import SimulationEngine

TESTS=['tests/unit/hangma/test_route_transition.py',
    'tests/unit/hangma/test_route_transition_composition.py',
    'tests/unit/hangma/test_route_transition_audit.py',
    'tests/unit/hangma/test_route_transition_v35_parity.py',
    'tests/unit/hangma/test_route_hu_witness.py',
    'tests/unit/hangma/test_public_tile_counts.py']


def main():
    """fixture评分不算当前S02强度；真实业务入口尝试数单独计费。"""
    counts={'rule_analyze_attempts':0,'fixture_vip_score_attempts':0,
        'fixture_legacy_score_attempts':0,'fixture_failed_score_attempts':0,
        'fixture_world_starts':0,'fixture_world_advances':0}
    calls=[];changes=[]
    with (_project_file(_PROJECT_ROOT, HERE/'UNIT-INPUTS.jsonl.gz')).open('x+b') as stream:
        capture=ScoringInputCapture(stream,limits=ScoringInputCaptureLimits(64<<20,256<<20,64))
        with installed() as identity:
            try:
                for cls,name,key in [(HangmaRules,'analyze','rule_analyze_attempts'),
                    (SimulationEngine,'start','fixture_world_starts'),
                    (SimulationEngine,'advance','fixture_world_advances')]:
                    original=getattr(cls,name)
                    def counted(*args,_original=original,_key=key,**kwargs):
                        counts[_key]+=1
                        return _original(*args,**kwargs)
                    changes.append((cls,name,original));setattr(cls,name,counted)
                for name,key in [('score_vip_route','fixture_vip_score_attempts'),
                    ('score','fixture_legacy_score_attempts')]:
                    original=getattr(ActionValueExecutor,name)
                    def scored(self,view,_original=original,_key=key):
                        counts[_key]+=1
                        row={'kind':_key,'source_sha256':hashlib.sha256(self.source.encode()).hexdigest(),
                            'fixture_only_not_current_S02_strength':True}
                        row['input_capture']=asdict(capture.store(view.candidate_view()))
                        try:
                            if not row['input_capture']['saved_before_score']:
                                raise RuntimeError('fixture实际完整输入未保存，禁止评分')
                            result=_original(self,view)
                            row['result']=asdict(result);row['status']='SCORED'
                            return result
                        except BaseException as exc:
                            counts['fixture_failed_score_attempts']+=1
                            row['status']='FAILED';row['error']=type(exc).__name__+': '+str(exc)
                            raise
                        finally:
                            row['operations']=self.last_operation_count;calls.append(row)
                    changes.append((ActionValueExecutor,name,original));setattr(ActionValueExecutor,name,scored)
                code=pytest.main(['-q','-p','no:cacheprovider',*TESTS])
            finally:
                for cls,name,original in reversed(changes):setattr(cls,name,original)
        final=capture.finish()
    with (_project_file(_PROJECT_ROOT, HERE/'MECHANICAL-CONTRACT-RESULT.json')).open('x') as stream:
        json.dump({'schema':'t124-mechanical-public-regression/1','pytest_exit_code':int(code),
            'tests':TESTS,'native_identity':identity,'actual_unit_fixture_costs':counts,
            'actual_fixture_scores':calls,'complete_capture':final,
            'new_model_authors':0,'natural_whole_table_instances':0,
            'current_S02_score_attempts':0},stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({'pytest_exit_code':int(code),'costs':counts,
        'capture_valid':final['terminal']['terminal_valid']},ensure_ascii=False))
    return int(code)


if __name__=='__main__':raise SystemExit(main())
