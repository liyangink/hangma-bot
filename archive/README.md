# 测试房间历史 Token 与配置归档

## 用途

官方测试房间用完即弃，但 Token 与房间配置是审计线索（对应 `runs/slot-*/`
下的运行记录）。本目录按时间归档已完成使命的测试房间凭据与配置，
保持 `token/` 与 `configs/` 只保留当前有效的赛事材料。

## 命名约定

文件夹名 `<YYYYMMDD-HHMM>-test-room-t_<赛事id>`，其中时间取该房间
四份 Token 文件的发放时间（文件 mtime，当前观察，非官方字段）。
每个文件夹内：

- `config.json`：当时的房间配置原文；`token_file` 已重写为指向
  归档内 Token 的仓库根相对路径，文件夹自洽（若房间仍存在可复跑，
  复跑入口：`python scripts/run_test_room.py --config archive/<文件夹>/config.json`）；
- `tokens/<槽位>.txt`：四身份 Token 原文（青龙 / 白虎 / 朱雀 / 玄武）。

## 归档清单

| 文件夹 | 赛事 id | Token 时间（本地） | 当时策略 | 备注 |
| --- | --- | --- | --- | --- |
| `20260904-1641-test-room-t_714a42392cba` | `t_714a42392cba` | 2026-09-04 16:41 | weighted_heuristic | 原 M=1/Rounds=1 冒烟房间（前身 `test-room-m1r1`）；对应抓取样例存于 `tests/fixtures/official/captures/` |
| `20260904-1730-test-room-t_cee1db65a074` | `t_cee1db65a074` | 2026-09-04 17:30 | weighted_heuristic | 跨轮复用验收房间（runs 内 r6/r7 记录） |
| `20260904-1900-test-room-t_6c121bfda7e8` | `t_6c121bfda7e8` | 2026-09-04 19:00 | claim_if_legal | 测试房间验收房间（runs 内 r1—r4 记录） |
| `20260905-1653-test-room-t_9779c892550e` | `t_9779c892550e` | 2026-09-05 16:53 | claim_if_legal | 四线修复活场验收房（M=2 双桌；验收报告见 doc/implementation/reviews/test-room-acceptance-result-2026-09-05.md） |

## 安全提醒

- Token 是敏感凭证：归档仍留在私有仓库内，不进入日志、截图或对外输出；
  `run_test_room.py` 读取时只经环境变量传给子进程并全程脱敏。
- 测试房间空闲超时（默认 30 分钟）会自动关闭；归档配置能否复跑以
  平台房间实际状态为准，关闭后的房间仅作审计留档。
