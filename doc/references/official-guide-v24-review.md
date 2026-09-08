# 指南 v24：参赛令牌入口兼容审查

**v24 不改变 scoped 参赛令牌路径；测试房四身份可继续运行。全局令牌入口不因此放行。**2026-09-08 在测试房 `t_8aebcc286b39` 启动前，从官方 `GET /portal/api/guide/version` 抓取 v24（官方更新日期 2026-09-08）。[完整原始变更响应](official-guide-version-v24.json)与[请求来源及哈希](official-guide-version-v24-source.json)随代码保存。

官方确认：v24 删除匿名自注册 `POST /api/users`；非门户绑定的全局令牌在新匹配或新报名时返回永久条件 `403 PORTAL_BINDING_REQUIRED`。存量在途行为另有幂等例外。第⑤条明确 scoped 参赛令牌路径不变，包含测试房的四个 Bot 身份。

`OfficialTournamentSession` 本来就要求 `/api/me.tournament_id` 绑定目标房间并拒绝全局令牌。因此只在该入口的初始化与 scoped 阶段边界，将 v24 列为已审查 breaking 版本。原始 `changes` 不改写，全局 `KNOWN_GUIDE_VERSION=15` 不上调；新 v25 breaking 或畸形版本仍被拒绝。`OfficialAutoMatchSession` 的全局令牌入口仍使用原门禁，不能继承 scoped 例外。实际已审查版本列表进入初始化/阶段边界审计。

本次只解决参赛令牌被通用版本门误拦的问题，不修改规则、策略、HTTP 限速或动作提交。真实房间仍按当前校准范围核对 BaseScore=1、`YouCaiBiKao=false`，并作为抓打圈权限诊断；不据此发布自由赛候选。

验证：适配器相关 69 项通过，完整回归 4,071 项通过（42.89 秒）。新增测试读取本次官方快照，覆盖 scoped 初始化与阶段到位、下一版未知 breaking、畸形版本、全局令牌拒绝以及自动匹配未被误放行。
