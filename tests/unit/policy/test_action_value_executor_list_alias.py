"""通过公开评分入口验证局部嵌套列表的引用、切片与集合上限语义。"""

import pytest

from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.action_value_seeds import build_sample_view


@pytest.mark.parametrize("index", ["0", "-1"])
def test_indexed_nested_list_keeps_mutations(index):
    """普通索引应返回原对象；路线累加器依赖这种 Python 语义。"""
    source = f'''def score_actions(view):
    groups = [[]]
    groups[{index}].append(3)
    alias = groups[{index}]
    alias.append(4)
    return {{'status': 'ABSTAIN', 'reason': 'seven' if sum(groups[{index}]) == 7 else 'wrong'}}
'''
    batch = ActionValueExecutor(source).score(build_sample_view())
    assert batch.reason == "seven"


def test_slice_copies_outer_list_but_preserves_nested_references():
    """切片仅浅拷贝外层；切片中的内层对象仍与原列表共享。"""
    source = '''def score_actions(view):
    groups = [[]]
    copied = groups[:]
    copied.append([9])
    copied[0].append(3)
    return {'status': 'ABSTAIN', 'reason': 'correct' if len(groups) == 1 and sum(groups[0]) == 3 else 'wrong'}
'''
    batch = ActionValueExecutor(source).score(build_sample_view())
    assert batch.reason == "correct"


@pytest.mark.parametrize("setup", ["values = groups[0]", "values = groups[0][:]"])
def test_index_and_slice_retains_collection_limit(setup):
    """修复引用语义后，普通索引与切片仍不得绕过每个局部集合的上限。"""
    source = f'''def score_actions(view):
    groups = [list(range(4096))]
    {setup}
    values.append(4096)
    return {{'status': 'ABSTAIN', 'reason': 'unexpected'}}
'''
    with pytest.raises(WorkloadExceeded, match="集合"):
        ActionValueExecutor(source).score(build_sample_view())
