# 前端接入与重构指南 (Frontend API Contract)

本项目后端采用 **FastAPI + Redis**，为前端提供了一套干净、无状态、安全脱敏的 API。前端只需要实现人机验证、单账号展示、一键复制、三态使用结果反馈及无号兜底跳转即可。

---

## 1. 核心业务流程与时序

前端必须先询问下载目标，再揭示账号：

- 目标应用用户：优先已确认可下载目标应用的账号；登录成功后继续打开目标应用页面并确认是否出现下载按钮。
- 其他应用用户：优先已确认能登录 App Store 的账号；登录成功即完成目标，不显示目标应用相关步骤。
- 复制必须按顺序进行：复制 Apple ID → 打开 App Store 并输入账号 → 返回复制密码 → 登录后反馈。不得让两项同时保持在系统剪贴板的错误心智。

```text
[用户打开页面]
      │
      ▼
1. GET /api/v2/config (获取 Cloudflare Turnstile sitekey 与 action)
      │
      ▼
[用户完成 Turnstile 校验]
      │
      ▼
2. POST /api/v2/session/verify (提交 Turnstile token，后端下发 HttpOnly Session Cookie)
      │
      ▼
3. POST /api/v2/reveal-ticket (获取一次性消费票据 ticket)
      │
      ▼
4. POST /api/v2/accounts/reveal (提交 ticket，获得 1 个最佳可用账号 或 兜底购买链接)
      │
 ┌────┴────────────────────────┐
 │                             │
 ▼                             ▼
[展示账号卡片]               [展示无号兜底卡片]
(账号/密码一键复制)           (显示“购买专属外区+小火箭账号”按钮，跳转 purchase_link)
 │
 ▼
[用户在设备上尝试登录]
 │
 ├── 1. 成功且有小火箭 -> 点击【✅ 账号有效，能下载小火箭】
 ├── 2. 能登录但无小火箭 -> 点击【🟡 能登录，但没有小火箭】
 └── 3. 密码错误/验证码 -> 点击【❌ 无法登录 / 密码错误 / 需验证码】
 │
 ▼
5. POST /api/v2/accounts/feedback (提交反馈)
      │
      ▼
[自动回到步骤 3+4，获取同一会话未看过的下一个账号]
```

---

## 2. 通用请求规范

所有 `POST` 请求必须满足以下规范（否则后端安全拦截返回 `403`）：

1. **Headers 必须包含**：
   - `Content-Type: application/json`
   - `X-Requested-With: XMLHttpRequest`
2. **凭据传递**：
   - `fetch` 请求配置 `credentials: "same-origin"`（或 `include`），确保在第 2 步获取到的 Session Cookie 在后续请求中自动带上。
3. **缓存策略**：
   - `cache: "no-store"`

---

## 3. 接口详细契约

### ① 初始化配置：`GET /api/v2/config`

- **请求**：无 Header / Body 要求。
- **响应 (`200 OK`)**：
  ```json
  {
    "turnstile_site_key": "0x4AAAAAAEWphBwvKRMtrwrr",
    "turnstile_script_url": "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit",
    "turnstile_action": "reveal"
  }
  ```
- **前端动作**：加载 `turnstile_script_url` 脚本，并在容器元素上使用 `turnstile_site_key` 与 `turnstile_action` 渲染人机验证组件。

---

### ② 校验人机验证并建立会话：`POST /api/v2/session/verify`

- **请求 Body**：
  ```json
  {
    "token": "0.cf-turnstile-token-from-widget-callback"
  }
  ```
- **响应 (`204 No Content`)**：
  - 无 Body。
  - Response Headers 会设置 `Set-Cookie: __Host-aid_session=...; HttpOnly; Secure; SameSite=Strict; Path=/`。
- **异常响应**：
  - `403 Forbidden`：Token 无效或人机验证未通过，前端需调用 `turnstile.reset()` 重置验证码。

---

### ③ 获取取号票据：`POST /api/v2/reveal-ticket`

- **请求 Body**：`{}`
- **响应 (`200 OK`)**：
  ```json
  {
    "ticket": "tk_5tkNGBE-2Cur8lNeb4kloxzen_7ZxUXcKszMKdh7yqU",
    "expires_in": 30
  }
  ```
- **异常响应**：
  - `429 Too Many Requests`：请求过于频繁（IP 或会话限流）。

---

### ④ 获取单个账号：`POST /api/v2/accounts/reveal`

- **请求 Body**：
  ```json
  {
    "ticket": "tk_5tkNGBE-2Cur8lNeb4kloxzen_7ZxUXcKszMKdh7yqU",
    "intent": "target_app"
  }
  ```
  - `intent`：`target_app` 表示目标是图标所示应用，优先分配已确认可下载该应用的账号；`other_app` 表示下载其他应用，优先分配已确认能登录 App Store 的账号。
- **响应 A：成功获取到账号 (`200 OK`)**：
  ```json
  {
    "total": 1,
    "updated_at": 1787232000,
    "exhausted": false,
    "purchase_link": null,
    "accounts": [
      {
        "id": "acc_0891d29381c81ef4",
        "username": "example@icloud.com",
        "password": "ExamplePassword123",
        "region": "US",
        "status": "active",
        "last_synced_at": 1787231980,
        "features": []
      }
    ]
  }
  ```
  - `purchase_link`：只要后端配置了 `STORE_URL`，无论账号是否耗尽都会返回；前端据此始终提供“购买专属账号”的中途退出与最终兜底，不得硬编码店铺地址。

- **响应 B：账号已用尽或无可用账号 (`200 OK`)**：
  ```json
  {
    "total": 0,
    "updated_at": 1787232000,
    "exhausted": true,
    "purchase_link": "https://your-shop-address.example.com",
    "accounts": []
  }
  ```
  *说明：`exhausted: true` 时，前端应隐藏账号卡片，展示“当前暂无更多可用共享账号”，并渲染跳转到 `purchase_link` 的购买专属账号大按钮（若 `purchase_link` 为 `null` 则仅提示暂无账号）。*

---

### ⑤ 提交账号使用反馈：`POST /api/v2/accounts/feedback`

- **请求 Body**：
  ```json
  {
    "account_id": "acc_0891d29381c81ef4",
    "result": "shadowrocket_available"
  }
  ```
  - `account_id`：当前正在展示的账号 `id`。
  - `result` 枚举值：
    - `"shadowrocket_available"`：账号有效，且已购买/可下载小火箭。
    - `"shadowrocket_missing"`：能正常登录 App Store，但目标应用不可下载。
    - `"login_success"`：非目标应用路径中，已确认可以登录 App Store；该结果不声称目标应用的下载状态。
    - `"login_failed"`：账号锁定、密码错误或需要双重验证码。
- **响应 (`204 No Content`)**：
  - 反馈记录成功。
- **异常响应**：
  - `409 Conflict`：该账号已在当前会话反馈过，不可重复提交。
- **前端动作**：
  - 用户点击“成功达成目标”后，提交反馈并结束本次流程。
  - 用户点击“没能达成目标”或“登录不上”后，提交反馈，再自动进入下一轮取号流程（调步骤 ③ 获取新 ticket -> 调步骤 ④ 获取下一个账号）。
  - 前端显示层必须使用面向任务的三态文案，不直接暴露后端枚举名。

---

## 4. UI / 交互设计建议

1. **单屏专注**：卡片上只保留当前一个账号和密码，配备大而易点的一键复制按钮。
2. **警示信息**：顶部保留醒目提示：“仅在 App Store 登录下载，严禁在系统设置或 iCloud 登录！”
3. **流畅过渡**：点击反馈按钮后，显示轻微 Loading 动效，随后毫秒级切换为下一个账号。
4. **兜底转化**：账号用尽后，突出店铺购买链接的视觉重心，引导付费转化。
