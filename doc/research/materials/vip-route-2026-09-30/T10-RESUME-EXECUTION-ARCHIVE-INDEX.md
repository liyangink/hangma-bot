# T10 恢复执行原件归档索引

**本包保存真实失败探针、修后探针和记录工程桌小批；不授强度或发布。** 2026-10-01 归档 252 个文件、124,789,046 字节原件。逐成员从压缩包读回核验成功，两个分块拼接摘要与原压缩包相同。当前机器原件保留，Git 只提交归档及必要直接入口，避免重复保存庞大的完整桌 JSON。

清单：[ARCHIVE-MANIFEST.json](./evidence/t10-resume-execution-archive-1/ARCHIVE-MANIFEST.json)。归档整体 SHA-256：`ffb43834ed17656199d519af93562fed31ac07209cc2a7d14db55b4433d6237e`。

| 原件目录 | 内容与边界 |
| --- | --- |
| `evidence/t10-resume-execution-1/` | 事前登记、16 窗真实来源面板、首次 48 次评分入口；32 条解释格式失败原件及费用，没有完整桌 START |
| `evidence/t10-resume-execution-2/` | 修后另 START、48/48 窗口、16 完整桌实例/128 单局、完整输入、逐窗动作、结算、运行代码/数值后端快照、费用与先封清单 |

恢复时在仓库根目录按顺序拼接分块，核整体摘要，再解包；成员名称自带仓库相对路径。命令不会调用规则、模型或比赛。

```bash
cat review/vip-route-2026-09-30/evidence/t10-resume-execution-archive-1/execution-raw.tar.gz.part-* > /private/tmp/hangma-t10-execution-raw.tar.gz
shasum -a 256 /private/tmp/hangma-t10-execution-raw.tar.gz
tar -xzf /private/tmp/hangma-t10-execution-raw.tar.gz
```

不要覆盖本机已有原件；已有目录先按清单核其字节。本包不重复归档旧 T9 来源，重跑来源读取还需按其已有归档索引恢复旧原件。执行配置中的绝对来源路径保持原记录，归档本身不解决不同目录的来源迁移。

结论与下一步：[实际小批结果](./T10-RECORDING-PILOT-RESULT-AND-NEXT.md)、[恢复计划](./T10-RESUME-AND-CREDIT-DIAGNOSTIC-PLAN.md)。根核对全部原件、2,345 个 C 调用和 1,677 个完整输入；独立收尾只读原件，常规后续跑批不重复交审。
