"""从用户本次接手授权派生保守的三提案开发预算；不授予确认或发布权限。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import json
import sys
import datetime
HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / 'evidence/v4-impl/r9-gate2/run')))
from p12_authorization import unified_document

def main():
    """一次性写独立监督试运行配置，拒绝覆盖已冻结批次。"""
    out = _project_file(_PROJECT_ROOT, HERE / 'pilot')
    out.mkdir(exist_ok=True)
    auth = out / 'authorization.json'
    if auth.exists():
        raise SystemExit('已有冻结配置，不覆盖')
    doc = unified_document(batch_label='r9-takeover-supervised-pilot',
        authorization_id='r9-takeover-20260919-three-proposals',
        accounts={'tokens_input':393216, 'tokens_output':98304,
                  'tables_full':128, 'tables_partial':12, 'prefix_generation':12},
        issued_by='user request: 接手修复复核并推进进化搜索；root 设定保守批次上界',
        issued_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        legacy_alias=False)
    doc.update({'generation_call_limits':{'tokens_input':131072,'tokens_output':32768},
                'route':'supervised_candidate_development', 'autonomous_admission':False,
                'max_model_calls':3, 'max_proposals':3, 'repair_calls_count_in_total':True,
                'wall_clock_limit_seconds':3600,
                'scope':'离线开发，先一项 I1，通过后才基于真实反馈 M1；不打开确认集，不发布',
                'natural_panel_note':'每个 H/M 子面板 1 个完整桌赛 seed × 4 座位；小样本链路试运行，不构成效果证据'})
    auth.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n')
    settings = (_project_file(_PROJECT_ROOT, ROUTE / 'evidence/v4-impl/r9-admission/p25-dev-cards/glm/settings/glm-settings.yaml')).read_text()
    settings = settings[settings.index('llm-pi-ai:'):].replace('contextWindow: 1000000','contextWindow: 1000000\n          maxTokens: 32768')
    (out/'settings.yaml').write_text('# 独立监督试运行配置；maxTokens 为显式请求输出上界。\n'+settings)
    (out/'route.patch.yml').write_text('- id: settings\n  config:\n    path: '+str(out/'settings.yaml')+'\n    watch: false\n- id: agent-default-model\n  config:\n    provider: zai-coding-cn\n    model: glm-5.3\n')
    (out/'manifest.json').write_text(json.dumps({'schema':'sitin-supervised-author-channel/1',
        'target_model':{'provider':'zai-coding-cn','model':'glm-5.3'},
        'expected_request_config':{'provider':'zai-coding-cn','model':'glm-5.3',
                                   'reasoningEffort':'max','maxTokens':32768}}, indent=2)+'\n')
    print('pilot configuration frozen; no calls made')
if __name__ == '__main__': main()
