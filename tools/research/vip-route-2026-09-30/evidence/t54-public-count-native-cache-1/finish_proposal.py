"""生成正式测试及三份同步文档的隔离补丁；不修改运行中的main。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')

ARCH = '''## 2026-10-02 VIP构图公开计数复用

**研究VIP构图只复用完整公开输入对应的计数，不减少路线或重用旧未见容量。** `build_vip_route_scoring_view`在同步调用内开启`hangma.public_tile_counts.public_count_result_scope()`，原完整构图体和公开签名不变。规则模块按公开视图八字段＋严格／旧观察兼容标志复用冻结结果；历史原件强持有，全部嵌套字段按共享注解检查精确类型。未知注解、可变输入或超过4096事件的历史仍走原计数；本人暗牌、单列摸牌、座位和飘白容量每次按原函数重算。

每次作用域独占结果2048条、守卫16384条，饱和后原算。`ContextVar`隔离绑定，`RLock`保护显式复制上下文可能共享的对象；嵌套作用域另建缓存，异常和正常退出均关闭清空并恢复外层，逃逸上下文不再纳入新结果。规范值对象不得绕过冻结原地改写。缓存没有网络、文件、时钟、模型或隐藏信息依赖，紧急动作路径不使用复杂构图缓存。该变化须新依赖身份及工程／时限验证；T52原冻结源码和历史成绩不改写。证据见[T54隔离工程](../review/vip-route-2026-09-30/T54-NATIVE-PUBLIC-COUNT-CACHE.md)。

'''

CONTRACT = '''## 2026-10-02 构图内公开计数工程接缝

**新增`public_count_result_scope()`仅控制纯结果复用寿命；共享规则、图和评分语义不变。** 无输入，作为同步contextmanager使用且yield None；作用域内缓存完整公开视图八字段及`legacy_four_meld`对应的`PublicTileCounts`，最多2048结果／16384严格形状检查条目。全部字段按共享值对象注解确认exact类型，区分bool与int、固定四元组与变长元组；不支持注解或可变值原样回原函数，不新增计数拒绝、不吞原异常。

本人未见容量每次仍读取同态暗牌、单列摸牌、座位与飘白补记；未知、保守与精确证据不可互换。每个作用域独占缓存并强持有历史原件；嵌套、异常和正常退出通过token恢复外层并清空。ContextVar的对象引用显式继承时由RLock保护；关闭后旧上下文仅原算。规范冻结值不能通过__dict__/object.__setattr__主动改写。作用域只包同步全图构造，不含await、HTTP、模型、文件或时间。

`build_vip_route_scoring_view(request, config, *, limits=None)`公开参数、返回类型和完整事实不变；原函数体只移到内部实现。`HangmaRules.analyze`、`BotPolicy.choose`、执行器、视图／图v3及条件支付语义不升版。源码依赖摘要形成新工程身份；旧作者来源和历史效果只保留在原身份下，不凭等价性直接授新包发布。公共行为覆盖见[test_public_count_result_scope.py](../../tests/unit/hangma/test_public_count_result_scope.py)，完整输入与评分对账见[T54](../../review/vip-route-2026-09-30/T54-NATIVE-PUBLIC-COUNT-CACHE.md)。

'''


def main():
    targets = {
        'doc/architecture.md': ARCH,
        'doc/hangma-ai-bot-technical-plan.md': ARCH,
        'doc/implementation/interface-contracts.md': CONTRACT,
    }
    pieces, files = [], {}
    for name, section in targets.items():
        before = (_project_file(_PROJECT_ROOT, WORKTREE / name)).read_text()
        title, rest = before.split('\n\n', 1)
        after = title + '\n\n' + section + rest
        if name != 'doc/implementation/interface-contracts.md':
            after = after.replace(
                '公开牌计数只缓存不可变历史的领取证据解析（最多8条、每条至多4096事件），当前副露、牌河、守恒及未见容量照常重算；不缓存完整状态或隐藏信息。',
                '历史领取证据解析仍最多8条、每条至多4096事件；完整公开结果仅在上节VIP构图作用域按全字段键复用，未见容量照常重算，不缓存隐藏信息。', 1)
        pieces.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                           fromfile='a/' + name, tofile='b/' + name))
        files[name] = hashlib.sha256(after.encode()).hexdigest()
    test_name = 'tests/unit/hangma/test_public_count_result_scope.py'
    assert not (_project_file(_PROJECT_ROOT, WORKTREE / test_name)).exists()
    tested = (_project_file(_PROJECT_ROOT, HERE / 'edgecase-tests/test_public_count_result_scope.py')).read_text()
    pieces.extend(difflib.unified_diff([], tested.splitlines(True), fromfile='/dev/null', tofile='b/' + test_name))
    files[test_name] = hashlib.sha256(tested.encode()).hexdigest()
    raw = ''.join(pieces).encode()
    with (_project_file(_PROJECT_ROOT, HERE / 'TEST-AND-DOCS-PROPOSAL.patch')).open('xb') as stream:
        stream.write(raw)
    result = {'schema': 't54-test-docs-proposal/1', 'files_sha256': files,
              'patch_sha256': hashlib.sha256(raw).hexdigest(), 'tested_draft_copied_byte_exact': True,
              'main_source_modified': False, 'new_models_scores_worlds_tables': 0}
    with (_project_file(_PROJECT_ROOT, HERE / 'TEST-AND-DOCS-PROPOSAL.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({'test_and_docs_prepared': True, 'files': len(files)})


if __name__ == '__main__':
    main()
