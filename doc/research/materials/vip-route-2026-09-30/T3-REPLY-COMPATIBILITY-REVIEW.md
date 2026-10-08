# T3 回复格式兼容独立复核

日期：2026-09-30。**结论：冻结后的两文件修正通过本次独立复核，当前 Standards 与 Spec 均无未关闭发现。** 本次只审查思想格式兼容、原文保存与未发起请求的用量结算，不评价候选行为、完整桌赛表现或上线资格。

基点为 `09aea2e47887a1967256d4caf323cd9a80720637`；没有基点之后的已提交记录，本次对象是以下工作区差异：

```bash
git diff 09aea2e47 -- src/hangma_bot/offline/vip_eoh_generate.py tests/unit/offline/test_vip_eoh_generate.py
git log 09aea2e47..HEAD --oneline
```

独立复验时的 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `src/hangma_bot/offline/vip_eoh_generate.py` | `3115d8d2d9aa05947b08ef5ecfc7c470630b5a97cb084beffa0f0b98a9eee034` |
| `tests/unit/offline/test_vip_eoh_generate.py` | `346478c36e64451c69621c5e39129a0f591147745f7efd4dd8d6f49c1a38dbd7` |

## Standards

**结论：未发现本次差异违反已读仓库标准，也没有需要行动的代码异味。** 依据为[根目录规范](../../AGENTS.md)第 4、5、6、8 节和[测试规范](../../tests/AGENTS.md)。生成器仍属于离线模块；候选只进入受限执行器，没有增加线上模型闭环、规则来源或受控评分接口。中文说明解释了内存思想封套和失败历史约束；新增测试通过公开 `parse_vip_eoh_reply`、`run_vip_eoh_generate` 验证行为。

思想封套（`thought_envelope`，记录思想句是否带花括号）与格式版本只进入生成记录；没有修改固定框架合同、规则身份或 `score_actions(view)` 返回要求。兼容无花括号思想不补写模型思想，也不改原回复文件和摘要。执行源码继续使用旧解析器的首尾空白规范；`source_raw` 保存 Python 围栏中的原始正文，不能把两者混称为逐字原文。

命令及结果：

```bash
git diff --check 09aea2e47 -- src/hangma_bot/offline/vip_eoh_generate.py tests/unit/offline/test_vip_eoh_generate.py
```

结果为空，退出码为 0。另逐项检查了命名、重复逻辑、额外接缝和修改范围，未发现需要单列的异味。

限制：只审查这两文件与它们直接调用的旧解析器、账本；没有审查其他工作区改动。并发槽已满，本独立代理分别执行两轴复核，没有再启动子代理。未验证官方时限或发布门禁。

## Spec

**结论：无花括号单行思想可摄入；唯一机制 JSON、唯一 Python、精确字段、有序多父和 m2 数值变更约束继续成立。未发起模型请求的失败按已知零模型用量结算；发起后缺可信用量仍按原预留计费。** 规格依据为根代理本次明确任务，以及[接线计划](./T3-EOH-WIRING-PLAN.md)第 2、4、5 节。历史回复摄入（`replay`，读取已有回复封套而不发起新模型请求）继续区分人工格式夹具和来源自述的模型捕获。

复核中发现的边界已由根代理修复，再由本代理独立复验：

| 初始发现 | 与基点的关系 | 冻结后结果 |
| --- | --- | --- |
| 无花括号的纯空白前缀被接受为 `thought=''` | 本次新增兼容路径的退步；基点拒绝 | 非空检查拒绝；有花括号的空思想也拒绝 |
| Python 正文混入缩进的第二个围栏，旧解析器只取首段代码 | 基点已存在，不归因于本次引入 | 按 `^[ \t]*\x60\x60\x60` 计数，额外围栏拒绝，不再产生截断候选 |
| 思想含 U+2028/U+2029，视觉上为多行 | 原行分隔限制未覆盖 Unicode 分隔符 | `splitlines()` 检查拒绝 |
| 围栏头部的 `\s*` 吞掉 Python 正文首空行 | 基点已存在 | 围栏头部仅接受水平空白；首尾空行、注释和尾空格留在 `source_raw` |

独立定向命令：

```bash
.venv/bin/pytest -q tests/unit/offline/test_vip_eoh_generate.py -k 'plain_single_thought or plain_thought_compatibility or configuration_failure_before_call or empty_and_unicode or indented_extra_python or plain_thought_keeps or exact_reply_shape or ordered_multi_parent or numeric_literal_m2 or m2_rejects or m2_real_string or api_unknown_usage or api_exception_retains or same_output_dir or historical_model_replay'
```

结果：**32 passed, 45 deselected in 6.56s**。覆盖新增边界、精确机制键、重复 JSON 键、算子不匹配、多父顺序与去重、m2 实际变化及声明对应、已发起请求的未知用量、异常费用保留、历史用量不重复收费和同输出目录防覆盖。

此外通过公开解析接口构造无花括号的 `m2/e2` 人工材料：合法数值调整和完整两父声明通过；逻辑变化、漏参数声明、父代倒序和漏父声明全部拒绝。人工探针还核验 LF/CRLF 的原始源码正文、生成记录格式标签与原回复摘要、零模型费用、夹具身份，以及先前失败记录和账本行保持不变。探针复算见下文。

限制：测试中的假传输、机制和封套均为人工材料，不是新增模型输出。没有读取私有凭据、发起真实模型请求或运行完整桌赛。没有摄入那两份真实 GLM 捕获，也没有修改真实失败记录；真实摄入的来源链接与旧回复摘要仍须由后续证据链保留。本复核不为生成物发放行为改善、准入或发布结论。

## 原文、标签、零费用和失败历史的人工探针

此命令只调用公开生成接口；使用已有单元测试的人工批次和格式夹具辅助函数，在临时目录运行，结束后自动删除临时件。构造失败不会进入模型调用。

```bash
.venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, parse_vip_eoh_reply,
    run_vip_eoh_generate,
)

helpers = runpy.run_path('tests/unit/offline/test_vip_eoh_generate.py')
raw = '\n# 人工源码原文：保留注释与空格  \ndef score_actions(view):\n    return 2.0  \n\n'
braced = helpers['reply_text']('i1', raw)
plain = braced.replace('{人工测试联合机制}', '人工测试联合机制', 1)
a = parse_vip_eoh_reply(braced, 'i1', [])
b = parse_vip_eoh_reply(plain, 'i1', [])
assert a['source_raw'] == b['source_raw'] == raw
assert a['source'] == b['source'] == raw.strip()
assert parse_vip_eoh_reply(braced.replace('\n', '\r\n'), 'i1', [])['source_raw'] == raw.replace('\n', '\r\n')

with tempfile.TemporaryDirectory(prefix='vip-reply-review-') as directory:
    path = Path(directory)
    batch_file = helpers['batch_file'].__wrapped__(path)

    def broken_factory(*args, **kwargs):
        """人工模拟传输构造失败，没有网络请求或副作用。"""
        raise ValueError('人工配置失败，无模型请求')

    failed = run_vip_eoh_generate(batch_file=batch_file,
        out_dir=path / 'first-failure', operator='i1', backend='api',
        model='synthetic-request', backend_factory=broken_factory)
    old_bytes = (path / 'first-failure/generation.json').read_bytes()
    ledger_file = batch_file.with_suffix('.vip-eoh-ledger.json')
    old_row = json.loads(ledger_file.read_bytes())['reservations'][0]
    for account in ('model_calls', 'input_tokens', 'output_tokens'):
        assert failed['billing']['actual'][account] == 0
        assert failed['billing']['charged'][account] == 0
    packet, _ = build_vip_eoh_prompt(VipEohBatch.read(batch_file), 'i1', [])
    envelope = path / 'synthetic-fixture.json'
    helpers['fixture_envelope'](envelope, packet, plain)
    result = run_vip_eoh_generate(batch_file=batch_file,
        out_dir=path / 'plain-replay', operator='i1', backend='replay',
        reply_file=envelope)
    assert result['status'] == 'loaded_not_admitted'
    assert result['reply_format_version'] == 'vip-eoh-reply-format/2'
    assert result['thought_envelope'] == 'plain_single_line'
    assert result['artifact_role'] == 'format_fixture'
    assert result['is_model_output'] is False
    assert (path / 'plain-replay/reply.txt').read_bytes() == plain.encode('utf-8')
    assert result['reply_sha256'] == hashlib.sha256(plain.encode('utf-8')).hexdigest()
    assert (path / 'plain-replay/source-raw.py').read_bytes() == raw.encode('utf-8')
    assert result['source_raw_sha256'] == hashlib.sha256(raw.encode('utf-8')).hexdigest()
    for account in ('model_calls', 'input_tokens', 'output_tokens'):
        assert result['billing']['charged'][account] == 0
    assert (path / 'first-failure/generation.json').read_bytes() == old_bytes
    assert json.loads(ledger_file.read_bytes())['reservations'][0] == old_row
print('raw_source LF/CRLF PASS; plain_generation_metadata PASS; fixture_not_model PASS; zero_model_billing PASS; old_failure_unchanged PASS')
PY
```

Standards：0 项未关闭发现；Spec：0 项未关闭发现。已关闭的问题只证明解析与费用边界，不扩展为策略效果结论。
