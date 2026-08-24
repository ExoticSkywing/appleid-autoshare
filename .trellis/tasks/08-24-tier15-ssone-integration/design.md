# Tier-1.5 SSONE 接入技术设计

## 1. 设计目标

在不改变现有双 Tier-1 主链路、不泄露中间来源与登录凭据的前提下，为后端增加一个可关闭、可独立过期、可自动降级的 Session 鉴权 DOM 来源。

本任务只交付技术设计与开发验收依据；实现由后端同事负责。

## 2. 信任边界

```text
Deployment Secret Store
  └─ source_c URL + opaque Cookie header
                │
                v
Authenticated Source-C Poller
  ├─ strict TLS / timeout / size / redirect policy
  ├─ challenge-vs-content classifier
  ├─ bounded multi-sample fetch
  └─ strict semantic DOM parser
                │
                v
Independent Redis Slice: reserve_c
  ├─ fetched_at
  ├─ valid_until
  ├─ upstream_updated_at per account
  └─ normalized internal accounts
                │
                v
Existing aggregate → dedupe/rank → verified session/ticket → one-account reveal
```

- **不可信上游**：HTML、状态文案、时间、账号字段均视为不可信输入。
- **敏感配置区**：URL 和 Cookie 都是部署秘密，不属于代码配置常量。
- **内部临时状态**：Redis slice 可包含凭据，但不得持久化或暴露端口。
- **不可信浏览器**：继续使用现有单账号披露和反馈换号，绝不下发完整源池或来源信息。

## 3. 建议模块边界

后端同事应优先复用现有抽象，而非修改通用 DOM 适配器以塞入大量来源特例：

- `app/config.py`
  - 新增 `source_c_enabled`、`source_c_url`、`source_c_cookie`、轮询/采样/年龄参数。
  - 校验“启用才必填”，避免关闭储备源时阻塞主服务。
- `app/adapters/authenticated_dom_source.py`（建议命名）
  - 继承/复用 `BaseAdapter` 的网络限制。
  - 负责不透明 Cookie header、响应分类、有限采样与 SSONE 专用 DOM 解析。
  - 不把 Cookie 拆成多个业务字段，降低泄漏面和站点字段耦合。
- `app/services/aggregator.py`
  - 继续通过通用 `(adapter, interval)` 列表独立运行；第三来源异常不得影响其他 poller。
- `app/services/store.py`
  - 无需引入特殊 Redis 结构；复用独立 source slice。
  - 若当前 InternalAccount 不支持上游更新时间，增加仅内部字段或 adapter 侧以该时间映射 `last_synced_at`，但不能进入公共来源元数据。
- `scripts/live_probe.py`
  - 增加 source C 脱敏探针；只输出分类、数量、年龄、摘要。
- `tests/fixtures/`
  - 使用手工脱敏/虚构 HTML，不保存真实账号和 Cookie。

## 4. 配置契约（建议）

| 配置 | 默认 | 约束 |
|---|---:|---|
| `SOURCE_C_ENABLED` | `false` | 显式开关 |
| `SOURCE_C_URL` | 空 | 启用时必须是无 URL 凭据的 HTTPS URL |
| `SOURCE_C_COOKIE` | 空 | 启用时必填；secret 注入；禁止打印 |
| `SOURCE_C_POLL_SECONDS` | `300` | 必须大于单轮最大网络预算 |
| `SOURCE_C_SAMPLE_COUNT` | `3` | 建议范围 1–5 |
| `SOURCE_C_SAMPLE_JITTER_MS` | `250–750` | 实际可用 min/max 两项或统一上限 |
| `SOURCE_C_FRESHNESS_SECONDS` | `600` | 独立于 A/B；配置化 |
| `SOURCE_C_UPSTREAM_MAX_AGE_SECONDS` | `900` | 依据“来源更新时间”过滤 |
| `SOURCE_C_SLICE_TTL_SECONDS` | `1200` | 必须大于 freshness，仅供诊断清理 |

安全说明：环境变量在某些平台可被同权限进程或运维面板读取。生产优先 Docker/Kubernetes secret file 或平台 Secret 管理；如果项目现阶段只支持 env，至少确保 `.env` 权限、备份排除、日志脱敏和容器 inspect 权限受控。

## 5. 响应分类状态机

```text
HTTP fetch
 ├─ redirect/non-2xx/oversize/timeout → fetch_failed
 └─ 200
     ├─ browser-check fingerprint → challenge_returned
     ├─ login/auth fingerprint → auth_expired
     ├─ expected account container absent → markup_drift
     └─ expected container present
         ├─ strict parse yields 0 while groups claim available → parse_failed
         ├─ strict parse yields 0 and page explicitly reports empty → empty_pool
         └─ valid account(s) → sample_success
```

关键规则：`challenge_returned`、`auth_expired`、`markup_drift` 与 `empty_pool` 必须分开，便于运维采取正确动作；但这些细节不进入公共 API。

## 6. DOM 解析契约

### 6.1 容器范围

1. 根容器：`[data-sky-knowledge-shared-accounts]`。
2. 分组：`[data-sky-shared-account-group]`。
3. 账号项：在每个分组内定位 `.sky-shared-account-item`。
4. 字段：在同一个账号项内，以标签文本 `Apple ID` 和 `密码` 找到对应 `[data-sky-shared-account-value]`。

不得把全页所有 `data-sky-shared-account-value` 按顺序两两配对，因为页面导航区也可能出现邮箱，且 DOM 漂移时会产生跨卡片错配。

### 6.2 健康状态

- 分组头必须包含明确“可用”状态。
- 账号项必须含 `.sky-shared-account-status.is-ready` 且规范化文本为“正常”。
- 任一 unhealthy marker 命中账号项文本或相关属性即剔除。
- 不依赖单一图标 class 作为健康证据；图标只能作为辅助指纹。

### 6.3 时间语义

- `来源更新时间` → `upstream_updated_at`，代表供应商数据更新时间。
- `本站同步时间` → `relay_synced_at`，只用于内部诊断。
- 解析时明确站点时区；若页面无时区标识，应通过部署配置指定，禁止默认为运行容器本地时区。
- freshness 计算优先使用 `upstream_updated_at`；无该字段时按 `fetched_at` 计算但降低内部置信度。

## 7. 有界多采样算法要求

- 每轮最多 `sample_count` 个请求，串行执行并加入小抖动。
- 对每次成功样本进行严格解析，再按规范化 username 去重。
- 遇到挑战页/认证失效立即停止；其他单次瞬态网络失败由后端同事决定是否继续剩余预算，但不能重试无界化。
- 不以“已收集 6 个”为停止条件；实测 6 个只是研究样本，不是协议保证。
- 允许一轮只获得当前随机子集。产品目标是增加冗余，不是声称穷举供应商全池。

## 8. 聚合与排序

- 新来源返回与既有 `CandidateAccount` 兼容的对象。
- 全局以 username 大小写不敏感去重；冲突时依次比较：
  1. 明确健康状态；
  2. `upstream_updated_at`；
  3. `fetched_at`；
  4. 已有用户反馈质量分。
- 来源优先级不能向浏览器暴露，也不能让 Tier-1.5 无条件覆盖更新鲜的 Tier-1 记录。
- “正常”只证明页面宣称可用，不证明已购 Shadowrocket；质量反馈逻辑保持现状。

## 9. 失败与降级

- Source C 失败：不替换、不续期 slice；仅增加原因码计数。
- Source C 过期：从 fresh aggregate 排除。
- A/B 可用时：用户流程不受影响。
- 仅 C 可用时：是否允许 readiness 为 true 沿用当前“任一 fresh slice”语义，但运维面必须能看到主源全部失效这一退化状态。
- 紧急回滚：设置 `SOURCE_C_ENABLED=false` 并滚动重启，不需要迁移或删除其他 source slice；旧 C slice 因未被读取/过期自然清理。

## 10. 安全与隐私设计

- 公共 DTO 不添加来源字段。
- Cookie 不进入 `repr`、异常、metrics label、trace baggage、Sentry context。
- 指标 label 仅使用低基数内部 alias 和固定 reason code。
- 测试 fixture 使用 `user1@example.invalid` 等虚构数据。
- 聊天中已有 Cookie 视为泄漏凭据；开发/生产不得复用。
- 不实现自动绕过 WAF 或自动登录；遇到 challenge 只告警人工更新授权会话。

## 11. 验证矩阵

| 范畴 | 必验场景 |
|---|---|
| 配置 | disabled 无需 secret；enabled 缺 URL/Cookie 失败；非法 HTTPS/范围失败 |
| 网络 | 302、401/403、超时、超限、坏 UTF-8、挑战页 |
| 解析 | 正常 2 组、单组、多账号组、错序字段、缺密码、跨卡片、异常状态、重复账号 |
| 时间 | 合法时间、未来时间、超龄、无时区、缺来源时间 |
| 采样 | 1/3 次、重复随机样本、部分网络失败、认证失败中止、上限保证 |
| 存储 | C 独立 TTL；A/B 刷新不续期 C；C 失败不续期自身 |
| 聚合 | 跨源去重、冲突排序、反馈排名、最大 reveal 数量 |
| 泄漏 | URL/Cookie/域名/别名不出现在 public response、assets、logs、exceptions |
| 回归 | 双源关闭 C 的完整测试全部通过 |

## 12. 已知残余风险

- Session Cookie 会过期或被 WAF 绑定浏览器/IP，服务端 Worker 是否长期稳定需要部署环境实测；该风险是 Tier-1.5 定位而非 Tier-1 的核心原因。
- 对方可能修改 DOM 或服务条款；必须具备人工复核和一键禁用能力。
- 有限刷新只能提高发现轮转账号的概率，无法证明完整池覆盖。
- 一旦明文账号交付给真实用户，无法通过技术手段实现绝对防复制；现有 Turnstile、单次 ticket、单账号披露和频控只能提高滥用成本。
