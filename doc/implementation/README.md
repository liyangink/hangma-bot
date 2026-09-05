# 第一阶段实施导航

> 状态：接口基线 v1；实行受控变更  
> 日期：2026-09-03  
> 范围：可参加官方测试房间与测试赛事的可审计 MVP

## 1. 结论

MVP 后的审计增强实施入口为[审计增强实施方案](./audit-enhancement.md)（2026-09-05，待实施）：先补齐线上记录，再做跨节点归档与统一牌谱转换，最后补只读实时查看。本导航下文保留第一阶段基线；新的具体离线整理任务依该方案开展，不预建训练或模拟基础设施。

第一阶段只实现六个生产模块和两个启动入口：`kernel`、`hangma`、`policy`、`application`、`adapters/official`、`adapters/recording`、正式单身份入口和测试房间四身份入口。模拟、训练、模型、复杂赛事效用和通用基础设施暂不建目录、不冻结接口。

跨模块类型和端口已经写入：

- [`kernel/actions.py`](../../src/hangma_bot/kernel/actions.py)
- [`kernel/config.py`](../../src/hangma_bot/kernel/config.py)
- [`kernel/observation.py`](../../src/hangma_bot/kernel/observation.py)
- [`hangma/interface.py`](../../src/hangma_bot/hangma/interface.py) 与 [`hangma/engine.py`](../../src/hangma_bot/hangma/engine.py)
- [`policy/interface.py`](../../src/hangma_bot/policy/interface.py)
- [`application/contracts.py`](../../src/hangma_bot/application/contracts.py)

边界取舍和被否决方案记录在 [ADR-0001](../decisions/0001-freeze-mvp-module-contracts.md)，避免后续 Agent 重复引入已经排除的复杂度。

实施 Agent 先读根目录 `AGENTS.md`、所属模块目录的 `AGENTS.md`、[接口协议](./interface-contracts.md)和对应模块说明。接口文件由总体架构统一维护；模块 Agent 在接口背后实现，不得为方便局部实现而单方面改变字段或语义。

## 2. 可并行工作包

| 工作包 | 代码边界 | 指导文档 | 前置依赖 | 首要交付 |
| --- | --- | --- | --- | --- |
| 稳定类型 | `src/hangma_bot/kernel/` | [kernel](./modules/kernel.md) | 无 | 不可变动作、观察和配置 |
| 杭麻规则 | `src/hangma_bot/hangma/` | [hangma](./modules/hangma.md) | `kernel` 契约 | 由规则主 Agent 自行派发手牌数学、动作族、财神/结算子任务，最终交付完整动作族与独立紧急路径 |
| 启发式策略 | `src/hangma_bot/policy/` | [policy](./modules/policy.md) | `kernel`、规则契约 | 有序候选计划与保底策略 |
| 运行编排 | `src/hangma_bot/application/` | [application](./modules/application.md) | 三个核心契约 | 生命周期、多场监督、拒绝降级循环 |
| 官方适配 | `src/hangma_bot/adapters/official/` | [official adapter](./modules/official-adapter.md) | 应用端口、官方 v8 fixture | 传输、同步、动作门和端口实现 |
| 审计记录 | `src/hangma_bot/adapters/recording/` | [recording](./modules/recording.md) | `AuditSink` | JSONL 记录、汇总和验证器 |
| 四身份启动 | `scripts/`、`bootstrap.py` | [test room runner](./modules/test-room-runner.md) | 上述模块可组装 | 单身份入口和四进程测试入口 |

允许各 Agent 先用 Fake 消费或实现端口，不需要等待其他模块完成。跨模块集成只依赖冻结接口，不导入对方内部文件。

### 2.1 统一技术基线

- Python 3.11 作为最低生产版本，使用标准库 `asyncio`；场次任务采用结构化并发和显式取消。Python 3.11 引入的 `TaskGroup` 适合管理一组相关任务，但单场异常隔离仍需应用层按本项目语义处理，不能直接依赖默认“一错全取消”。[Python 3.11 asyncio 文档](https://docs.python.org/3.11/library/asyncio-task.html)
- 官方 HTTP 统一使用一个“每 Token 长生命周期”的 `httpx.AsyncClient`，显式配置连接池、连接/读取/写入/池等待超时；禁止在长轮询热循环中反复创建客户端。[HTTPX 异步客户端](https://www.python-httpx.org/async/)、[HTTPX 资源限制](https://www.python-httpx.org/advanced/resource-limits/)、[HTTPX 超时](https://www.python-httpx.org/advanced/timeouts/)
- 值类型优先标准库冻结 `dataclass`；第一阶段不引入运行时依赖注入框架、ORM、消息队列或 Agent 框架。
- 测试统一使用 `pytest` 与 `pytest-asyncio`；纯值契约可以保留标准库 `unittest`，二者都通过公开接口测试。[pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/en/stable/)
- 具体依赖版本在第一个实现 Agent 建立 `pyproject.toml` 和锁文件时固定；升级必须先跑契约、官方 fixture 与时间故障测试。

## 3. 集成顺序

1. 契约测试和保存的官方 v8 fixture 先通过。
2. 规则紧急路径、Fake 会话和审计内存实现打通最短竖切。
3. 接入官方测试房间，先跑 `M=1/Rounds=1` 的四 Token 全自动完赛。
4. 补齐规则动作族、409 明确拒绝降级、模糊提交封锁、序号恢复和审计验证。
5. 提升到目标 `M/Rounds`，执行网络、进程和磁盘故障注入。
6. 官方测试赛事是 MVP 发布门禁：验证报名/到位、多阶段、淘汰、重赛和新增场次。

完整门禁见[第一阶段验收标准](./mvp-acceptance.md)。

## 4. 变更协调

需要修改接口时，提出一个最小变更说明，至少回答：

1. 哪个已存在实现无法满足当前契约；
2. 为什么不能把复杂度隐藏在该模块内部；
3. 哪些调用方、Fake、fixture、契约测试和文档受影响；
4. 是否改变信息权限、截止时间、提交幂等性或审计关联键。

批准后由总体架构维护者一次性修改契约及文档，模块 Agent 再各自适配。禁止短期并存两套同义接口。
