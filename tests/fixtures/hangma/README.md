# hangma 规则金例夹具（2026-09-05 差分工作包）

> 本目录保存「禁胡门禁 + 胡牌判定误报修复」任务的回归夹具；
> 所有条目必须注明来源（房间 id/局号/指南版本/抓取日期）——tests/AGENTS.md 硬要求。
> 无 Token/Authorization；归档房间数据 API 免认证（房间 id 即凭证）。

## 来源

- 数据接口：`GET https://10.240.169.190:18080/api/test-rooms/{id}/games` 与
  `/api/test-rooms/{id}/games/{batch}/events`（免认证，房间级限速 5/s）。
  TLS 为内网自签证书，拉取工具使用不校验证书的本地上下文（仅针对该内网主机）。
- 抓取日期：2026-09-05（Asia/Shanghai）。
- 官方指南版本：v14（2026-09-05 抓取，`doc/references/official-guide-v14.txt`）；
  「碰后禁止胡牌」门禁出自指南变更日志 v1（2026-09-02，
  `doc/references/official-guide-version-v14.json` changes[version=1]）；
  「对局七对胡牌判定修复」同为 v1（2026-09-01）。
- 平台运行形态依据：`tests/fixtures/official/captures/state-draw-phase-t_714a42392cba.json`
  （2026-09-04 官方 /state 原始响应：my_hand 含刚摸的牌、drawn_tile 单列）。

## 文件

- `archived-rooms/t_6c121bfda7e8_b0.json`：房间 t_6c121bfda7e8、batch 0 事件流
  （批次与轮次复用重号，batch 0 解析为该房间最新一轮的场次 `t_6c121bfda7e8_r4_b0_t0`，
  见指南变更日志 v4「每轮批次从 0 重号」）。含四家开局手牌、逐事件摸/打/吃/碰与官方结算。
- `archived-rooms/t_cee1db65a074_b0.json`：房间 t_cee1db65a074，最新轮场次
  `t_cee1db65a074_r7_b0_t0`。
- `archived-rooms/t_714a42392cba_b0.json`：房间 t_714a42392cba，最新轮场次
  `t_714a42392cba_r4_b0_t0`（内含官方真实自摸胡：座位 2、round_ended seq 345、平胡 fan=1）。
- `golden-hu-shapes.jsonl`：差分发现的边界牌型（每条含 provenance）。
  3 例为「摸牌双计」修复前的胡牌假阳性（官方实际未胡），1 例为官方真实胡金例。

## 拉取与对拍工具

- 拉取：`tests/unit/hangma/archived_room_tools.py`（可执行脚本，限速 5/s，重跑刷新本目录）。
- 重放差分：`tests/unit/hangma/test_hu_differential_replay.py`——离线重放四家视角，
  每次摸牌处引擎胡牌判定 vs 官方 round_ended 实际结果，全程无网络依赖。
