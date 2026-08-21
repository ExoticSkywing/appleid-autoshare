# Apple ID AutoShare — Production v2

生产级双源聚合、短时保鲜、人机验证、单账号披露与用户结果反馈服务。公开的 v1 明文接口已移除。

## 已实现

| 能力 | 实现 |
|---|---|
| 双源采集 | JSON 与 DOM 适配器独立轮询；URL/Referer 仅由环境注入 |
| 数据清洗 | 严格健康状态、邮箱/密码校验、同卡片同后缀配对、坏状态过滤 |
| 新鲜度 | 每源 Redis slice 记录不可后延的 `valid_until`；请求时只聚合仍新鲜的 slice |
| 防重放 | Turnstile 服务端校验 → HttpOnly 会话 → Redis 单次 `GETDEL` ticket |
| 防刷 | IP + Session Redis 固定窗口限流；默认无 CORS |
| 上游隔离 | API/SPA 不返回 source 字段；日志仅记录内部 alias、结果、耗时、数量 |
| 浏览器体验 | 每次只披露一个账号；用户反馈后选择下一账号，同一会话不重复 |
| 质量反馈 | 确认有小火箭优先；未知账号其次；能登录但无小火箭再次；无法登录最后。反馈仅限本会话已展示账号且只能提交一次 |
| 运维 | 非 root 镜像、只读文件系统、支持直连宿主机外部 Redis、默认暴露指定端口、健康/就绪探针 |

## 重要安全边界

浏览器一旦合法收到某个账号明文，操作者就能检查、复制或转发它。Turnstile、短会话、单次 ticket、一次仅披露一个账号、限流和源站隔离只能提高批量抓取成本、收窄滥用窗口，**不能提供 DRM，也不能承诺“彻底防爬”**。用户反馈属于弱信号，不等同于系统独立验证；系统只在会话绑定、单次提交和排序降级约束下使用它。

浏览器端 HMAC `dynamic_secret` 也没有采用：可供 JavaScript 使用的密钥必然可被客户端提取或复现，不能形成可靠授权。

## 新鲜度说明

每个上游 slice 默认最多有效 60 秒。45 秒轮询在正常网络下有有限余量；90 秒轮询与“所有记录永不超过 60 秒”存在物理冲突，因此 Source B 会在第 60 秒失效并进入 fail-closed 空窗，直到下一次成功抓取。

如业务要求硬性 60 秒 SLO，请在得到上游许可后，把**所有**轮询周期降至 30–40 秒或更短，为请求超时、处理时间和调度抖动保留余量。系统不会通过刷新聚合池来伪造上游新鲜度。

## 配置

```bash
cp .env.example .env
openssl rand -hex 32  # 分别生成 ID_HMAC_SECRET / STATE_HMAC_SECRET
openssl rand -hex 32  # 生成 REDIS_PASSWORD
chmod 600 .env
```

必须填写：

- `SOURCE_A_URL`
- `SOURCE_B_URL`
- `SOURCE_B_REFERER`（仅该上游实际需要时）
- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET_KEY`
- `TURNSTILE_EXPECTED_HOSTNAME`
- 三个随机密钥/密码

生产模式拒绝 Turnstile 测试模式、短 HMAC 密钥、不安全 Cookie、缺失的源地址或非 HTTPS 源地址。

## Cloudflare Turnstile

在 Cloudflare 控制台创建 Widget：

1. Hostname 只允许正式域名；不要把生产 Site Key 放行 `localhost`。
2. 前端 action 使用 `reveal`，服务端同时校验 `success`、`hostname`、`action`。
3. Secret 只放在服务器 `.env`，绝不能进入前端或仓库。
4. Token 最长有效约 5 分钟且单次使用；失败时前端重置 Widget。

本地/CI 应使用 Cloudflare 官方测试 Key，或仅在非 production 环境显式开启项目 test mode。生产环境 `TURNSTILE_TEST_MODE=true` 会启动失败。

## 启动与验证

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:${APP_HOST_PORT:-18740}/healthz
curl -fsS http://127.0.0.1:${APP_HOST_PORT:-18740}/readyz
```

- `/healthz`：进程存活。
- `/readyz`：Redis 可用，且至少有一个未过期 source slice。
- 单个上游可以独立失效并被排除；`/readyz` 为 200 只表示至少一个来源可服务，不代表双源都健康。持续出现 `poll_failed alias=<alias>` 时应修复或更换该来源配置。
- 默认只监听 `127.0.0.1:18740`，请通过反向代理和 HTTPS 对外发布。

## 宿主机 Redis 复用与部署

如果目标服务器已经通过宝塔/1Panel 或原生方式安装了 Redis（例如运行在宿主机 `6379` 端口）：

1. `docker-compose.yml` 已经配置了 `extra_hosts: ["host.docker.internal:host-gateway"]`，容器可以直接通过 `host.docker.internal` 连接宿主机 Redis。
2. 在新服务器的 `.env` 中指定外部 Redis 连接串即可（建议使用独立的 db 库如 `/1`，避免与宝塔中其他站点冲突）：
   ```dotenv
   REDIS_URL=redis://:你的Redis密码@host.docker.internal:6379/1
   REDIS_PREFIX=autoshare:v2
   ```
3. 在新服务器上一键构建并启动应用：
   ```bash
   docker compose up -d --build
   ```

## 反向代理与真实 IP

默认 `TRUST_PROXY_HEADERS=false`，应用只信任 socket 对端 IP。生产必须设置 `PUBLIC_ORIGIN=https://你的正式域名`；状态变更接口会精确校验 `Origin` 并拒绝 `Sec-Fetch-Site: cross-site`。

只有满足以下条件后才可开启：

1. 应用端口仍只绑定 loopback/私网，无法被公网绕过；
2. 反代会**覆盖**而非透传客户端提供的真实 IP Header；
3. Cloudflare 场景建议源站只允许 Cloudflare IP，或使用 Tunnel / Authenticated Origin Pull；
4. 然后设置 `TRUST_PROXY_HEADERS=true` 与 `PROXY_IP_HEADER=CF-Connecting-IP`。

否则攻击者可伪造 Header 绕过 IP 限流。

## 测试

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy app
```

所有测试数据使用 `.invalid` 域名和合成密码；禁止把真实凭据写进 fixture、日志或报告。

## 故障处理

| 现象 | 处理 |
|---|---|
| `/healthz` 200，`/readyz` 503 | 查 Redis 健康与应用日志中的 alias/result/count；不查看或打印上游 body |
| Reveal 503 | 当前没有新鲜 slice，等待下一次成功轮询或检查上游配置 |
| Reveal 403 | 会话/ticket 无效或 ticket 已使用，重新 Turnstile 验证 |
| Reveal 429 | IP/Session 达到窗口上限，等待窗口重置；不要直接关闭限流 |
| Turnstile 失败 | 核对 Hostname、Action、Secret 与源站出网；不要切换生产 test mode |

Redis 在 Compose 中禁用 AOF/RDB，容器停止后凭据缓存消失，这是有意的 fail-closed 设计。

可选配置 `STORE_URL=https://...` 必须使用 HTTPS；配置后每次账号披露都会返回该链接，因此前端可同时提供中途退出购买与账号耗尽后的最终兜底。

`Dockerfile` 使用两阶段构建；运行阶段只包含已安装的虚拟环境与应用。当前基础镜像仍使用可维护 tag。正式受控发布前，应在 `Dockerfile` 与 `docker-compose.yml` 固定经批准的镜像 digest，并纳入常规补丁升级流程。
