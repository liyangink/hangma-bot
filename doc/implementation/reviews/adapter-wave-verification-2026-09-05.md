# Adapter 聚焦波验证记录（2026-09-05，测试房 t_9779c892550e r3 接管会话）

> 背景：四项修复（小修批/重复提交根治 F1-F4/SSE 接入）在真实平台 mid-game 接管会话中验证。
> 全套件 1288 passed。会话运行至第 8 局时收口（效果指标连续 3 个检查周期稳定）。

## 决定性指标（vs 基线与修复前会话）

| 指标 | 09-04 基线（整晚） | 同房修复前会话 | **本会话（r3 接管，SSE 开启）** |
| --- | --- | --- | --- |
| 重复 pass 409 | 816 次 | 236 次/16 场 | **0**（738 次提交，8 局×4 身份） |
| SSE 降级 | —（未接入） | 2/场（首连 AttributeError） | **0**（帧驱动持续健康） |
| hu 409 误报 | 89%（194/218） | 0 | **0**（6 接受/0 拒） |
| 开局 dto_invalid（"0w"） | 0.6/场 | 2.0/场 | **0**（占位符归一化生效） |

## 排障记录（接入过程发现并修复的两个真实缺陷）

1. **transport extensions 形态**：`open_sse_stream` 把 `httpx.Timeout` 对象放入 `extensions["timeout"]`，httpcore 以 `.get("pool")` 读取 → AttributeError 首连即失败。修复：`timeout.as_dict()`；回归测试在真实 httpx 客户端层拦截 send 断言 dict 形态（test_sse_transport_regression.py）。S1 交付的 fake 流测试绕过 httpx 层未暴露——其自列"待官方环境实测"风险的实证。
2. **notify 回调契约**：`_deliver_frame` 以 `await` 调用 on_frame（要求协程），集成层初版传同步函数 → `await None` TypeError。修复：`async def _on_sse_frame`。

**降级梯子实战验证**：缺陷 1 触发时四身份会话自动永久降级长轮询并留 `sse_degraded` 审计，打牌不中断（25 秒内各 52-54 次提交）——设计承诺在真实故障下兑现。

## 遗留（非阻塞）

- `closed:true` 终止帧活场样本：会话收口时 r3 场未完（8/16 局，运行中）；STREAM_ENDED 路径已有单测，样本待场终随手捕获。
- 会话完整跑完后可再跑一次终检脚本对照（可选）。
