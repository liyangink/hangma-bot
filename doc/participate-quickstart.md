# 正式赛参赛说明

环境：macOS 11 或更新版本的 Apple Silicon Mac，已安装 Git 并接入比赛网络。首次安装需要联网；程序自动准备 Python 和依赖，无须手动编译。当前不支持 Windows。

## 1. 拉取程序

```bash
git clone --filter=blob:none --sparse https://github.com/liyangink/hangma-bot.git
cd hangma-bot
git sparse-checkout set configs doc prebuilt scripts spectator src tests token
```

该方式只检出参赛代码和发布依赖，无须下载 `review/`、`datasets/` 等离线数据。当前 P0 使用 `approved-v3` 发布包；资格证明已随 `prebuilt/` 交付，仍执行原摘要校验。v3重新冻结更新后的主线源码，P0公式、规则、二进制和原批准资格保持。测试赛使用的v2快照保留；更新代码后重新执行`check`生成匹配当前包的配置。

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
