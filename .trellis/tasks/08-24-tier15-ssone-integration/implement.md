# Tier-1.5 SSONE 后端实施交接计划

> 本文是交给后端同事的执行清单，不授权本安全研究角色编写或运行实现代码。

## 0. 开发前置门槛

- [ ] 阅读 `prd.md` 与 `design.md`，确认 Tier-1.5 定位、降级边界及秘密管理要求。
- [ ] 阅读项目 `.trellis/spec/backend/index.md`、错误处理、日志与质量规范。
- [ ] 不使用聊天中已经暴露的 Cookie；由项目负责人提供轮换后的测试凭据，并通过本地 secret 注入。
- [ ] 确认目标站点访问与自动轮询得到账号所有者/服务授权，轮询频率不违反使用约束。
- [ ] 从干净工作树创建后端任务分支；不得在当前实验性前端分支直接混入未经隔离的后端改动。

## 1. 配置与启动校验

- [ ] 增加 Source C 开关、URL、opaque Cookie、采样、轮询、freshness、来源时间最大年龄和时区配置。
- [ ] 实现“disabled 不要求 secret；enabled 时 fail-fast”的校验。
- [ ] 更新 `.env.example`，只写空占位符和安全注释。
- [ ] 确认配置对象、异常与启动日志不会打印 Cookie。

**验证：** 配置单测覆盖开关、缺失值、非法范围、非法 URL、生产模式。

## 2. 专用鉴权 DOM Adapter

- [ ] 复用 BaseAdapter 网络边界，并注入不透明 Cookie header。
- [ ] 增加挑战页、登录页、预期页面、空池和结构漂移分类。
- [ ] 实现同账号项语义配对，不允许全页顺序配对。
- [ ] 严格校验“分组可用 + 账号正常 + 无异常 marker”。
- [ ] 解析来源更新时间与中间站同步时间，执行时区/未来时间/超龄校验。
- [ ] 有界多采样、去重、抖动和认证失败快速中止。

**验证：** 使用完全虚构的脱敏 HTML fixtures；禁止把真实响应保存到仓库。

## 3. Aggregator 与 Redis Slice 集成

- [ ] 将 Source C 以独立 poller 注册，关闭时不实例化、不请求。
- [ ] 复用独立 source slice，确保 `valid_until` 不被其他来源刷新。
- [ ] 空结果、认证失败、挑战页、结构漂移均不得替换或续期旧 slice。
- [ ] 聚合时跨源去重并遵循 freshness/质量排序，不暴露来源。
- [ ] Source C 失败时 A/B 继续服务。

**验证：** 以可控时钟覆盖刷新、过期、失败、恢复、跨源冲突。

## 4. 可观测性与运维告警

- [ ] 增加固定低基数 reason codes：`ok`、`empty_pool`、`auth_expired`、`challenge_returned`、`markup_drift`、`upstream_stale`、`network_failed`。
- [ ] 指标仅记录 alias、计数、耗时、最后成功时间，不记录 URL/Cookie/账号。
- [ ] 认证连续失败阈值告警与结构漂移告警分开。
- [ ] 编写凭据轮换 Runbook 与一键禁用/回滚步骤。

## 5. 公共契约回归

- [ ] 不增加任何公开 source 字段或诊断 endpoint。
- [ ] 保持 Turnstile → session → ticket → reveal → feedback/换号流程。
- [ ] 保持单账号披露；不将一次多采样得到的完整池直接下发浏览器。
- [ ] 证明静态资源和 API 不包含目标域名、Cookie 名、供应商组及内部 alias。

## 6. 开发验证命令（由后端同事按项目环境执行）

后端同事应使用项目已有工具链，至少完成：

1. 全量 `pytest`（新增 adapter/config/store/aggregation/negative security tests）。
2. Ruff / mypy 现有门禁。
3. 公共泄漏扫描脚本。
4. Docker Compose config/build。
5. 本地 Redis + Turnstile test mode E2E：
   - Source C disabled 回归；
   - Source C fixture/mock enabled；
   - Source C challenge/expired 自动降级；
   - 单次 ticket 防重放；
   - 用户失败反馈后换到另一账号。
6. 经授权 live redacted probe：只输出状态分类、数量、时间年龄和摘要哈希。

## 7. Review Gates

- [ ] **规格审查**：逐条映射 PRD R1–R8 和 Acceptance Criteria。
- [ ] **安全审查**：重点检查 secret 泄漏、错误透传、挑战页误判成功、跨卡片错配、失败续期、无界采样。
- [ ] **运维审查**：确认凭据轮换、告警、开关、回滚可执行。
- [ ] **回归审查**：关闭 Source C 时双 Tier-1 生产行为与现有版本一致。

## 8. 交付物

- Source C 专用 Adapter 与测试。
- 配置项与 `.env.example` 更新。
- Aggregator/Redis 集成及回归测试。
- Live redacted probe 支持。
- Cookie 轮换与故障 Runbook。
- 安全泄漏扫描报告、测试报告、Compose 验证结果。
- PM 可核验的任务状态、分支/工作区和阻塞项。

## 9. 阻塞条件

出现以下任一情况不得宣称完成：

- 新凭据在部署 Worker 中持续返回浏览器挑战，且无法证明会话适合服务端轮询。
- 需要把 Cookie 写入代码或镜像才能运行。
- 页面结构无法实现同卡片确定性配对。
- Source C 失败会影响 A/B 或导致 stale slice 续期。
- 公共输出/日志/静态资源扫描发现来源或凭据泄漏。
- 未获得目标站点授权或轮询权限存在争议。
