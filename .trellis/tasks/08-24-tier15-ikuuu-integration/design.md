# Tier-1.5 iKuuu 接入技术设计 (Technical Design)

## 1. 架构组件划分

```text
┌────────────────────────────────────────────────────────┐
│               Environment / Secret Store               │
│  - SOURCE_D_ENABLED (bool)                             │
│  - SOURCE_D_URL (string)                               │
│  - SOURCE_D_COOKIE (string, secret)                    │
│  - SOURCE_D_POLL_SECONDS (int, default 300)            │
└──────────────────────────┬─────────────────────────────┘
                           │ Injects
                           ▼
┌────────────────────────────────────────────────────────┐
│           IkuuuSourceAdapter (BaseAdapter)             │
│  - GET /user/get-appleid with injected headers         │
│  - Validates ret == 1 and payload shape                │
│  - Computes valid_until = min(expire_time, now + TTL)  │
└──────────────────────────┬─────────────────────────────┘
                           │ Yields CandidateAccount
                           ▼
┌────────────────────────────────────────────────────────┐
│               Aggregator & Redis Store                 │
│  - Key: `<prefix>:source:ikuuu`                        │
│  - Ephemeral Slice with strict valid_until             │
└────────────────────────────────────────────────────────┘
```

## 2. 核心模块设计

### 2.1 Adapter 实现建议 (`app/adapters/ikuuu_source.py`)
* 继承现有 `BaseAdapter`；
* 构造请求携带 `Cookie`、`Referer` 与 `X-Requested-With: XMLHttpRequest`；
* 严格解析响应 JSON，若捕获到 `ret != 1` 或网络异常，返回空列表并记录脱敏指标。

### 2.2 契约与 DTO 映射
```python
# 响应数据转换规范
CandidateAccount(
    username=data["ios_apple_id"].strip(),
    password=data["ios_apple_id_password"].strip(),
    region="US"  # 默认按外区/自营池归类
)
```

## 3. 错误状态机与降级机制

| 响应状态 / 行为 | 判定结果 | 处理动作 |
| :--- | :--- | :--- |
| `HTTP 200` + `ret == 1` | 成功可用 | 提取账号，根据 `expire_time` 写入 Redis Slice |
| `HTTP 200` + `ret != 1` | Cookie 失效 / 无权限 | 记录 `poll_auth_failed alias=ikuuu`，清空/不续期该 Slice |
| `HTTP 4xx / 5xx` / 超时 | 网络或上游故障 | 触发通用错误捕获，直接降级，依赖主源 |
| JSON 字段缺失 / 格式异常 | 结构漂移 | 丢弃并记录 `parse_error alias=ikuuu` |
