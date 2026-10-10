# 共享离线工具

参赛程序仍从 `scripts/` 启动。这里保存进化、运维和回归实际使用的工具代码，完整研究输入和运行结果保存在本机。

- `offline/sitin/`：生成、回复解析、候选装载及相关回归。
- `offline/vip_evolution/`：当前进化驱动和复用的评估辅助代码。
- `offline/free_match/`：自由赛外部控制、原件校验和赛后处理；真实玩家仍由正式入口装配。
- `offline/free_match/runtime/closed_discard_repair.py`：对指定摘要的第19房取证源码生成独立窄修复，只准备离线模块，拒绝覆盖旧文件，不启动玩家；[证据与范围](../doc/research/astra-evolution-20261010/FREE-READINESS.md)。
- `research/`：现有回归依赖的研究工具，保留来源目录以便核对；当前操作按研究索引选择入口。
- `research/white-count-audit-2026-10-09/`：修复后的RF1报价探针、门清期权价保护与160单局单臂装配；[公开视图复验](../doc/research/lowwhite-160-20261009/WHITE-GAP-RECHECK.md)区分活动与收益，效果阶段继续用已验证的配对驱动。
- `research/astra-evolution-2026-10-10/`：完整十桌各十六单局的父子同牌山、真四席配对驱动，独立根汇总及听牌形状／实际摸牌次序审计。新包装在choose入口计入候选真实经过时间，仍须另过线上原截止并发门；范围和固定门见[Astra计划](../doc/research/astra-evolution-20261010/PLAN.md)。
- `research/astra-evolution-2026-10-10/freeze_fast160.py`：验实际候选和native来源，为[独立快速版](../doc/research/astra-evolution-20261010/FAST-V2.md)另冻新阶段根和原数值门；不启动池，不继承旧效果或批准。
- `research/astra-evolution-2026-10-10/freeze_integrated160.py`：核最终隔离组合根、实际候选／执行及四模式草稿，为[集成候选](../doc/research/astra-evolution-20261010/INTEGRATED.md)另冻来源和新根，不继承父代批准。
- `research/astra-evolution-2026-10-10/stage160_adaptive.py`：按事前一槽→十槽资源声明复用原经过时钟worker；只有原池自然退出与负门证据，或主agent核验工具handle的释放收据后扩池。算法、原预算、种子和门不随资源变化调整。
- `research/astra-evolution-2026-10-10/owned_stage160/`：已核有限监督源码及14项回归，直接拥有十工作进程，原序调用经过时钟worker；故障自然排空、硬异常只回收自己拥有的进程。需要独立冻结声明和单池授权，不能用部分完成数据过效果门；[使用范围](research/astra-evolution-2026-10-10/owned_stage160/README.md)。
- `research/astra-evolution-2026-10-10/roles160.py`：两池完整阶段的庄闲暴露、三类付款及角色胡牌比率补充报告；根内四席先合并计数、保留零分母未知，避免用付款总额替代每个角色单局的表现。不改变冻结效果门或授发布资格。

共享合同与原路径映射见 [研究索引](../doc/research/INDEX.md)。`HANGMA_OFFLINE_DATA_ROOT` 可以指定包含 `review/`、`datasets/` 等子目录的本机数据根。未配置时，工具兼容本机原目录；原件缺失明确报错，不自动下载或启动新任务。

精选数据在 `tests/fixtures/research/` 中，仅供测试。测试进程显式设置 `HANGMA_OFFLINE_TEST_FIXTURES=1`；正常研究优先读取本机原件。运行输出使用 `artifacts/` 或 `.private/`，不新增整批数据到共享工具目录。

自由赛控制器的只读帮助：

```bash
.venv/bin/python tools/offline/free_match/rf1_controller.py --help
```

已经启动的独立冻结运行根继续使用其原入口和原字节。切换运行根需要自然终态、原件完整、资源释放及同 Token owner 锁核验，不因本次目录整理重新匹配。
