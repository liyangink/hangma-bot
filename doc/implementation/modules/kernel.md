# `kernel` 实施说明

## 交付结果

提供所有模块共同使用的稳定、不可变值对象，并在类型层面隔离玩家可见信息与未来模拟的完整世界。第一阶段只修改 `src/hangma_bot/kernel/`。

## 实施重点

- 为规范牌值和官方牌值建立适配器侧显式映射，不能让官方字符串散落到业务模块。
- 手牌序列不能排序或转集合；普通紧急弃牌依赖 `my_hand[-1]`。
- 已确认快照字段 `phase/last_discard/hand_counts/god.baotou/god.chain_count/god.catch_play` 必须有规范类型；校验座位范围、四家向量长度、动作参数和正数配置。昂贵业务校验不放入构造函数。
- 提供稳定序列化函数时显式写 schema version，不直接把 `dataclasses.asdict()` 当长期格式。
- `CompetitionContext` 只保存已观察事实；未来晋级规模、截线和概率不放入本模块。

## 完成定义

- 公开类型、中文 docstring、相等性和序列化测试齐全。
- 动作封闭联合与 `action_key` 覆盖所有动作种类。
- 信息泄漏和手牌顺序回归测试通过。
- 不存在对其他业务模块或基础设施库的依赖。
