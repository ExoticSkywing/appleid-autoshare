# Tier-1.5 iKuuu 后端实施交接计划 (Implementation Plan)

> 本任务供后端开发同事对接使用。

## 1. 实施清单

### 阶段一：配置与环境对接
- [ ] 在 `app/config.py` 中添加 `SOURCE_D_ENABLED`、`SOURCE_D_URL`、`SOURCE_D_COOKIE`、`SOURCE_D_POLL_SECONDS` 配置项与校验逻辑。
- [ ] 在 `.env.example` 中补充示例模板（凭据处留空）。

### 阶段二：Adapter 开发
- [ ] 创建 `app/adapters/ikuuu_source.py`，继承 `BaseAdapter`。
- [ ] 实现针对 `/user/get-appleid` 的请求组装与 JSON 安全解析。
- [ ] 增加对 `expire_time` 的时间戳校验与有效截断。

### 阶段三：Aggregator 编排与合流
- [ ] 在 `app/api.py` 的生命周期中，当 `SOURCE_D_ENABLED=True` 时将该 Adapter 注册进 Aggregator 轮询队列。
- [ ] 确保与 Redis Source Slice（`alias=ikuuu`）的存取契约对齐。

### 阶段四：单元测试与门禁验证
- [ ] 编写 `tests/test_ikuuu_source_adapter.py`，覆盖正常解析、鉴权失败、字段缺失及超时等异常用例。
- [ ] 运行 `pytest`、`ruff check`、`mypy` 确保全量通过。
- [ ] 运行敏感信息泄漏检测脚本，确保源码中无明文 Cookie 和源站域名。
