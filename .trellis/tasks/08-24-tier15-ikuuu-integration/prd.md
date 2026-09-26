# Tier-1.5 iKuuu 鉴权 JSON 源接入需求 (PRD)

## 1. 业务目标与来源定位

### 1.1 来源定位与业务价值
为 `Apple ID AutoShare` 系统新增受控的 **Tier-1.5 鉴权自营储备源 (`SRC-04-IKUUU-API`)**。
该源具有付费会员强隔离保护，专为 Shadowrocket（小火箭）维护，账号纯净度与抗改密能力极高，属于**小火箭专用号池的绝对主力保底源**。

### 1.2 号池分类与定位架构
系统当前确立两大核心分发阵营：
1. **🚀 小火箭专用核心池 (Shadowrocket Pool)**：
   - 主力核心：`SRC-IKUUU` (`reserve_d`)（自营号，已购 Shadowrocket，带精确有效期）
   - 备用核心：`SRC-QINGFENG` (`qingfeng`)（清风自营池，待源站补号后无缝合流）
2. **🌐 通用美区池 (General iOS Pool)**：
   - `SRC-APPSTORE-AUTOS` (`source_a`) 与 `SRC-FNBAIDU` (`source_b`)（适合非小火箭/Nextin/跨区通用应用下载）
2. **零泄漏原则**：对外 API 及前端 SPA 严禁暴露该站点的任何域名、Cookie、品牌标识（如屏蔽 `ikuuu` 专有字样）或源站错误信息。
3. **安全降级**：若该源 Cookie 失效（如返回 `ret != 1` 或 HTTP 401/403/500），系统必须平滑降级并触发内部告警，不影响整体主流程。

---

## 2. 调研事实与协议分析 (Reconnaissance Findings)

* **数据端点**：`GET https://<CONFIGURED_HOST>/user/get-appleid`
* **协议类型**：REST JSON API
* **请求头依赖**：
  * `Cookie`: 包含用户态凭据（`uid`, `key`, `email`, `PHPSESSID` 等）
  * `X-Requested-With`: `XMLHttpRequest`
  * `Referer`: `https://<CONFIGURED_HOST>/user/tutorial?os=ios&client=openvxs`
* **原始响应 Schema**：
  ```json
  {
    "ret": 1,
    "msg": "获取成功",
    "data": {
      "ios_apple_id": "string (email)",
      "ios_apple_id_password": "string",
      "expire_time": 1787593041
    }
  }
  ```
* **特性与边界**：
  * 单 Session 下多次调用返回当前绑定的有效账号及相同的 `expire_time`；
  * 数据结构稳定，无需 DOM 解析，无结构漂移风险。

---

## 3. 功能与非功能需求 (Requirements)

### 3.1 接入与清洗需求
1. **配置驱动**：端点 URL、Cookie 字符串、拉取间隔由环境变量/Secret 动态注入，代码中禁止硬编码任何凭据与域名。
2. **清洗与标准化**：
   * 校验 `ret == 1`；
   * 校验 `ios_apple_id` 为合法邮箱且 `ios_apple_id_password` 非空；
   * 转换并映射为系统内部标准 `InternalAccount` DTO。
3. **时效与过期管理**：
   * 优先使用响应中的 `expire_time`（Unix 时间戳）与系统配置的 `MAX_SOURCE_FRESHNESS` 取较小值作为该 Slice 的 `valid_until`。

### 3.2 安全与防御需求
1. **凭据机密性**：Cookie 凭据严禁输出至日志、公开监控或前端 DTO 中。
2. **隔离与混淆**：向前端下发该源账号时，前端通用展示，隐藏上游元数据。

---

## 4. 验收标准 (Acceptance Criteria)

- [ ] 后端通过环境变量 `SOURCE_D_ENABLED=true` 显式控制开启/关闭。
- [ ] 成功请求返回 `ret=1` 时，账号正确解析并存入 Redis 对应 Source Slice。
- [ ] 当 Cookie 过期（如 `ret=0` 或非 200 响应）时，记录脱敏错误日志，对应 Slice 不入库，系统无异常崩溃。
- [ ] 单元测试覆盖有效响应、Cookie 异常、网络超时及数据结构畸变等场景（使用 Mock 数据）。
