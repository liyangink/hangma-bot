# 自由赛盯盘操作

**用途：**自由赛自动房的一次参赛由 `scripts/run_auto_match.py` 完成；连续盯盘由 `scripts/auto_match_watch_loop.sh` 每 60 秒调用一次幂等的 `scripts/auto_match_watch.sh`。后者负责发现会话、下载已完赛牌谱、结算账本，并在允许时续开下一房。运行状态以本机账本和审计为准，历史交接文档不代表当前进程状态。

## 启动前

按[运行与赛后操作](operations.md#2-启动测试房间与赛事)准备网络代理例外和单个全局 Token。连续盯盘的现行入口读取 `configs/auto-match.local.json` 与 `token/global/全局自由赛token`；凭证路径只在私有运行配置中维护，不在报告或命令输出中打印内容。先检查配置的赛事模式、审计目录、策略名称和冻结包摘要，并确认同一 Token 没有其他参赛进程。当前策略与接线结论见[研究证据索引](../review/INDEX.md)。

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

房间结束后，watchdog 先核对本地终局、下载官方牌谱，再将房分写入账本；`stopped=true` 只阻止续开，不阻止结算。若巡检返回退出码 3，查看 `runs/auto-match-watchdog/session-*.log` 的脱敏终态与对应 `artifacts/sessions/` 审计，不用重复开房掩盖异常。需要重新封存、转换或规则核验时，按[赛后处理](operations.md#4-完赛后下载封存与复核)使用 `scripts/audit_tool.py postgame`；具体房次的接线结论与取证脚本从[研究证据索引](../review/INDEX.md)进入。

官方响应 `timeout(kind=response)` 常是正常过牌终态。判断接线漏行动时，核对当时合法动作、冻结策略首选、同相位权威快照、请求排队、动作 POST 结果和官方事件，不能仅按 `timeout` 次数下结论。
