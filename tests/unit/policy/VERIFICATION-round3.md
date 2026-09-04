# rules-policy 第 3 轮返工验证记录（波 wv9）

> 结论：本包本轮无 finding（评审确认 4 个新 findings 全部属于 runtime-protocol 与 assembly-audit）。
> 本包无代码改动；以下为 NF 修复落盘后的全仓与定向回归验证记录。

## 验证时间

2026-09-04（第三轮返工裁决后，NF 修复落盘后的当前工作树）

## 验证命令与结果

| 命令 | 结果 |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q` | **1043 passed**（4.44s；当时树）→ 终验回基 **1054 passed**（2026-09-04 最终门禁，NF3/NF4 与信号回归落盘后） |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONASYNCIODEBUG=1 .venv/bin/python -m pytest -p no:cacheprovider tests/unit/hangma tests/unit/policy -q -W error::RuntimeWarning -W error::ResourceWarning` | **618 passed**（1.47s） |

## 结论

- 全仓与 rules-policy 定向（含 asyncio-debug + warnings-as-errors）均无回归。
- rules-policy（hangma/policy 源码与 tests/unit/hangma|policy）本轮零改动；F2 修复（discard 分支计数校验）保持闭环。
