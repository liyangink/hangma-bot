# 共享离线工具

参赛程序仍从 `scripts/` 启动。这里保存进化、运维和回归实际使用的工具代码，完整研究输入和运行结果保存在本机。

- `offline/sitin/`：生成、回复解析、候选装载及相关回归。
- `offline/vip_evolution/`：当前进化驱动和复用的评估辅助代码。
- `offline/free_match/`：自由赛外部控制、原件校验和赛后处理；真实玩家仍由正式入口装配。
- `research/`：现有回归依赖的研究工具，保留来源目录以便核对；当前操作按研究索引选择入口。

共享合同与原路径映射见 [研究索引](../doc/research/INDEX.md)。`HANGMA_OFFLINE_DATA_ROOT` 可以指定包含 `review/`、`datasets/` 等子目录的本机数据根。未配置时，工具兼容本机原目录；原件缺失明确报错，不自动下载或启动新任务。

精选数据在 `tests/fixtures/research/` 中，仅供测试。测试进程显式设置 `HANGMA_OFFLINE_TEST_FIXTURES=1`；正常研究优先读取本机原件。运行输出使用 `artifacts/` 或 `.private/`，不新增整批数据到共享工具目录。

自由赛控制器的只读帮助：

```bash
.venv/bin/python tools/offline/free_match/rf1_controller.py --help
```

已经启动的独立冻结运行根继续使用其原入口和原字节。切换运行根需要自然终态、原件完整、资源释放及同 Token owner 锁核验，不因本次目录整理重新匹配。
