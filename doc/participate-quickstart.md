# 正式赛参赛说明

环境：macOS 11 或更新版本的 Apple Silicon Mac，已安装 Git 并接入比赛网络。首次安装需要联网；程序自动准备 Python 和依赖，无须手动编译。当前不支持 Windows。

## 1. 拉取程序

```bash
git clone https://github.com/liyangink/hangma-bot.git
cd hangma-bot
```

## 2. 检查赛事

```bash
bash participate.sh check
```

按提示粘贴报名 Token，确认显示的赛事正确。此命令不会启动比赛。

## 3. 启动比赛

```bash
bash participate.sh start
```

保持终端运行，程序自动参赛直至结束。
