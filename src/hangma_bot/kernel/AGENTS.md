# `kernel` 模块实施规范

## 目标与边界

本模块只保存跨模块稳定、不可变且可序列化的值对象。先阅读仓库根目录 `AGENTS.md`、`UBIQUITOUS_LANGUAGE.md` 和 `doc/implementation/interface-contracts.md`。

- 可以定义：牌、座位、动作、动作窗口、玩家观察、官方已观察赛事上下文和不可变运行配置。
- 禁止定义：HTTP DTO、规则算法、策略评分、文件记录器、系统时钟读取和完整世界状态。
- 禁止依赖 `hangma`、`policy`、`application` 或 `adapters`。
- `PlayerObservation` 不得出现他家手牌、未来牌墙或赛后结果；手牌必须保留官方顺序。
- 四家向量和二维座位集合固定按座位 0—3，新增字段必须写清顺序、单位、可空条件和信息权限。

## 接口变更规则

`actions.py`、`config.py` 和 `observation.py` 是第一阶段共享接口基线，不代表实现已经完成。实施 Agent 不得单方面改名、删除字段或改变语义；确需修改时先提出契约变更并更新接口协议和术语表，让所有消费模块的契约测试同时通过。

## 验收标准

- 公共类型均有中文 docstring，值对象默认不可变。
- `Action` 是封闭联合类型，不用带大量可空字段的通用字典。
- `action_key()` 对相同动作确定性一致，不包含 Token 或进程随机值。
- 类型可被标准库序列化层稳定转换，且相等性测试通过。
- 信息泄漏测试证明改变隐藏牌不会改变同一 `PlayerObservation`。
