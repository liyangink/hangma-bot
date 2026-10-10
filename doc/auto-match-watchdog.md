# 自由赛盯盘操作

**2026-10-10当前：**[低白优化任务接手的RF1独立运行根](research/lowwhite-160-20261009/FREE-MATCH-TAKEOVER.md)在第19房自然结束后因门禁未通过停止续打，当前没有玩家运行。独立只读取证修复已完成，旧运行根和失败门保留，尚未激活新根或恢复续赛；见[第19房诊断与边界](research/astra-evolution-20261010/FREE-READINESS.md)。算法仍RF1，正式默认P0。当前根和状态命令以接手入口为准，不重启历史watchdog或建立重复定时任务。

**2026-10-09第18房修复历史：**当时相位拒绝停续通过129项回归与18房审计复扫后恢复自动续赛；该状态已由上方第19房停续现状替代。

**2026-10-09初始入口（已由上方接手入口替代）：**[G37-RF1独立冻结根续赛](research/materials/vip-route-2026-09-30/evidence/t227-rf1-default-and-live-1/README.md)。当时用户已恢复自由赛，唯一watch启用自动续，独立后台按完整桌分账；测试房160单局压力测试不会自动续。不要重启此旧入口或下方历史入口。

**2026-10-05 当前实验入口：**T110-S02使用[T191 free_v7自动续赛](../review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/LIVE-WATCHDOG.md)，算法原公式保持，main已整合明确拒绝后合法备用和四作用域接线。先用其`free_watchdog.py status`核真实玩家；自然完赛先接续，独立后台统计。常驻后台直接续赛，不依赖Codex定时任务；已删除的`t110` heartbeat不恢复。旧T179控制已关，禁止恢复T179、T170、T165或下述历史循环；测试房不自动续。

**历史通用入口：**自由赛自动房的一次参赛由 `scripts/run_auto_match.py` 完成；旧连续盯盘由 `scripts/auto_match_watch_loop.sh` 每 60 秒调用一次幂等的 `scripts/auto_match_watch.sh`。后者负责发现会话、下载已完赛牌谱、结算账本，并在允许时续开下一房。以下保留其运维说明，不是当前 T110 的默认启动步骤。运行状态以本机实际进程和审计为准。

## 启动前

按[运行与赛后操作](operations.md#2-启动测试房间与赛事)准备网络代理例外和单个全局 Token。连续盯盘的现行入口读取 `configs/auto-match.local.json` 与 `token/global/全局自由赛token`；凭证路径只在私有运行配置中维护，不在报告或命令输出中打印内容。先检查配置的赛事模式、审计目录、策略名称和冻结包摘要，并确认同一 Token 没有其他参赛进程。当前策略与接线结论见[研究证据索引](research/INDEX.md)。

本机账本是 `runs/auto-match-watchdog/auto-match-watchdog-state.json`（`runs/` 当前兼容旧目录的符号链接）。首次接手先**只读**检查 `stopped`、已结算房数和最后房号：

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

state = json.loads(Path('runs/auto-match-watchdog/auto-match-watchdog-state.json').read_text())
rooms = state.get('rooms', [])
print({'stopped': state.get('stopped'), 'rooms': len(rooms),
       'last_room': rooms[-1]['room_id'] if rooms else None})
PY
```

## 运行与暂停

一次巡检用 `bash scripts/auto_match_watch.sh`；**这不是只读命令**：在账本允许且无现有会话时，它可能调用官方匹配接口开房。需要连续巡检时，在保持运行的终端执行 `bash scripts/auto_match_watch_loop.sh`。macOS 入口会使用 `caffeinate` 防止休眠，避免错过短暂可下载的终局窗口。`run_auto_match.py` 会以独立会话进程运行；盯盘循环和参赛进程不是同一个进程。

要在当前房结束后停止续房，先在账本上加锁设置 `stopped=true`。这一步只改变本地续房许可，不会中断已开房间：

```bash
.venv/bin/python - <<'PY'
import fcntl
import json
import os
import tempfile
from pathlib import Path

directory = Path('runs/auto-match-watchdog')
ledger = directory / 'auto-match-watchdog-state.json'
with (directory / '.auto-match-watchdog.lock').open('a+') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    state = json.loads(ledger.read_text())
    state['stopped'] = True
    fd, temporary = tempfile.mkstemp(prefix='.watchdog-stop-', dir=directory)
    with os.fdopen(fd, 'w') as output:
        json.dump(state, output, ensure_ascii=False, indent=2)
        output.write('\n')
    os.replace(temporary, ledger)
print('已阻止下一房；当前房继续自然结算')
PY
```

待当前房出现在账本 `rooms` 且终局审计完整后，再停止盯盘循环本身。现行 `auto_match_watch_loop.sh` 不会因为 `stopped=true` 自动退出，而是每 60 秒继续做空巡检；不要以终止参赛进程代替停续房。恢复之前应重新核对策略、包摘要、官方指南及运行配置，再按同一加锁方法将 `stopped` 改回 `false`。

## 结算与问题定位

房间结束后，watchdog 先核对本地终局、下载官方牌谱，再将房分写入账本；`stopped=true` 只阻止续开，不阻止结算。若巡检返回退出码 3，查看 `runs/auto-match-watchdog/session-*.log` 的脱敏终态与对应 `artifacts/sessions/` 审计，不用重复开房掩盖异常。需要重新封存、转换或规则核验时，按[赛后处理](operations.md#4-完赛后下载封存与复核)使用 `scripts/audit_tool.py postgame`；具体房次的接线结论与取证脚本从[研究证据索引](research/INDEX.md)进入。

官方响应 `timeout(kind=response)` 常是正常过牌终态。判断接线漏行动时，核对当时合法动作、冻结策略首选、同相位权威快照、请求排队、动作 POST 结果和官方事件，不能仅按 `timeout` 次数下结论。
