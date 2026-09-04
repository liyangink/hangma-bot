# 官方 v8 契约 fixture

这里保存用于适配器契约测试的官方响应样本。每个文件内 `_meta` 注明端点、
HTTP 状态、指南版本、抓取日期与证据类型。

- 证据类型分两类：
  - `official-snapshot`：来自官方平台并完成脱敏的真实响应（如指南版本快照，
    另见 `doc/references/official-guide-version-v8.json`）；
  - 文档重建：官方接口文档（`doc/official-platform-api-v2.md`，v8，抓取 2026-09-03）
    记录了字段与结构，但尚未在官方测试房间抓取到完整响应样本。此类文件在
    `_meta.evidence` 中标注，接入官方测试房间后必须用真实抓取替换。
- 已删除 Token、`Authorization`、Cookie 和个人标识；`_meta` 为本地证据标注，
  不是官方字段，解析测试读取时会剥离。
- 覆盖：正常快照、pending、增量事件、`gap=true`、终局、碰窗口、409 与未来
  breaking 版本；阶段切换样本见 `tournament_*.json`。
- fixture 是协议证据，不是杭麻规则本身的权威证明。
