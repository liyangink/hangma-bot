# 测试房间与正式入口实施说明

## 交付结果

用同一个单身份运行入口支持测试赛事和正式赛事；测试房间入口读取四个 Token，启动四个完全隔离的子进程。

## 拓扑

```text
run_test_room.py
  ├─ run_participant.py --identity A → 最多 M 个场次
  ├─ run_participant.py --identity B → 最多 M 个场次
  ├─ run_participant.py --identity C → 最多 M 个场次
  └─ run_participant.py --identity D → 最多 M 个场次
```

`M` 是每个身份的同时场数，不是 Token 数。第一阶段不做同进程四身份、多租户依赖注入或共享模型。

## 配置与守护

- 配置最少包含 `mode`、固定 `base_url`、`expected_tournament_id`、四个身份槽位及其 Token 引用、策略名和审计根目录。
- Token 可以集中保存在私有仓库专用运行配置，但显示和记录时只使用脱敏 `participant_id`。
- 每个子进程有限次数重启并有退避；一个身份退出或失败不主动终止其他身份。
- 重启必须重新执行身份/目标核对并从权威状态恢复，不能重放内存中的动作命令。

## 完成定义

- 本地 Fake、官方 `M=1/Rounds=1`、目标并发三种模式均可一条受控命令启动。
- 四身份各有独立连接资源、进程状态和审计路径。
- 汇总显示每身份终态、场次数、最终分、超时、409、模糊提交和审计完整性。
- 正式入口不加载其他三个测试 Token，避免误接。

