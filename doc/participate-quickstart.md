# 正式赛参赛说明

环境：macOS 11 或更新版本的 Apple Silicon Mac，已安装 Git 并接入比赛网络。首次安装需要联网；程序自动准备 Python 和依赖，无须手动编译。当前不支持 Windows。

## 1. 拉取程序

```bash
git clone https://github.com/liyangink/hangma-bot.git
cd hangma-bot
```

普通克隆已包含参赛程序、共享工具和精选回归夹具；完整离线历史已从 Git 移除。当前正式赛默认 P0 `approved-v5`，测试房、测试赛事和自由赛默认 G37-RF1 `v2` 包装。此次仅重新绑定共享源码，算法、规则、二进制和原批准资格保持。更新代码后重新执行 `check`，生成匹配当前发布包的配置。

## 2. 检查赛事

```bash
bash participate.sh check
```

按提示粘贴报名 Token，确认显示的赛事正确。此命令不会启动比赛。

## 3. 启动比赛

```bash
bash participate.sh start
```

可提前启动；阶段之间自动等待，无须重新启动。保持电脑联网、终端运行，程序自动参赛直至结束。报名和到位须在赛事规定时限内完成。
