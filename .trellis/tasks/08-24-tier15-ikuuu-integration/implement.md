# Tier-1.5 iKuuu 后端实施交接计划 (Implementation Plan)

> 本任务供后端开发同事对接使用。

## 1. 实施清单

### 阶段一：配置与环境对接
- [ ] 在 `app/config.py` 与运行环境中确认配置项生效（当前主站漂移为 `https://ikuuu.top/user/get-appleid`，Referer 设为 `https://ikuuu.top/user/tutorial?os=ios&client=openvxs`）。
- [ ] 注入最新有效的会员 Cookie 凭据。

### 阶段二：Adapter 代码时钟容错微调
- [x] 检查 `app/adapters/ikuuu_source.py` 第 138 行，对 `expire_time <= current` 加入 60~120 秒的时钟容差，避免因上游服务器与本地服务器的时钟微小差异误判为 `schema_drift` 异常。

### 阶段三：Aggregator 编排与合流
- [x] 确认在 `app/api.py` 的生命周期中，当 `SOURCE_D_ENABLED=True` 时将该 Adapter 注册进 Aggregator 轮询队列。
- [x] 确保与 Redis Source Slice（`alias=reserve_d`）的存取契约对齐。

### 阶段四：单元测试与门禁验证
- [x] 运行 `pytest`、`ruff check`、`mypy` 确保全量通过。
- [x] 启动服务验证分发模式 `DELIVERY_SOURCE_MODE=all` 或 `DELIVERY_SOURCE_MODE=ikuuu_only`，确认带有 `features=["shadowrocket_purchased"]` 的专属账号正常进入 Redis 活跃池。
