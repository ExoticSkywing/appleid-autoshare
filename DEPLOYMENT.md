# 🚀 AppleID 智能共享与引导系统 — 生产部署手册

本项目基于 **FastAPI + Redis + 原生精细化响应式前端** 构建，专为非技术用户提供直觉式的海外 Apple ID 引导分发、安全教学与专属账号转化。

生产环境推荐使用 **Docker Compose** 进行一键标准化容器交付与隔离运行。

---

## 一、部署前准备

### 1. 基础环境依赖
- **操作系统**：Ubuntu 20.04 / 22.04 LTS 或 Debian 11 / 12（推荐）
- **必备工具**：Git、Docker (>= 24.0)、Docker Compose (>= 2.20)
- **前置反向代理**：Nginx / OpenResty / 宝塔 / 1Panel（负责 SSL 终止与域名绑定）

```bash
# Ubuntu / Debian 快速安装 Docker 环境
curl -fsSL https://get.docker.com | bash
systemctl enable --now docker
```

---

## 二、源码克隆与环境配置

### 1. 拉取仓库代码
```bash
git clone git@github.com:ExoticSkywing/appleid-autoshare.git /data/appleid-autoshare
cd /data/appleid-autoshare

# 切换到生产分支
git checkout experiment/discord-colorway
```

### 2. 生成并配置 `.env` 生产环境变量
拷贝示例配置：
```bash
cp .env.example .env
```

使用 `openssl` 生成两个 64 位的安全密钥：
```bash
openssl rand -hex 32  # 作为 ID_HMAC_SECRET
openssl rand -hex 32  # 作为 STATE_HMAC_SECRET
openssl rand -hex 16  # 作为 REDIS_PASSWORD
```

编辑 `.env` 文件，填入核心配置项：
```ini
APP_ENV=production
APP_HOST_BIND=127.0.0.1
APP_HOST_PORT=18740

# 1. 必填密钥
ID_HMAC_SECRET=填入生成的32位以上随机字符
STATE_HMAC_SECRET=填入生成的32位以上随机字符
REDIS_PASSWORD=填入生成的Redis密码

# 2. 账号源配置（根据你的上游数据源填入）
SOURCE_A_URL=https://upstream-a.example.com/api
SOURCE_A_POLL_SECONDS=45

# 3. 域名与安全
PUBLIC_ORIGIN=https://appleid.yourdomain.com
COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
PROXY_IP_HEADER=X-Forwarded-For

# 4. 人机验证（Cloudflare Turnstile）
TURNSTILE_SITE_KEY=0x4AAAAAA...
TURNSTILE_SECRET_KEY=0x4AAAAAA...
TURNSTILE_EXPECTED_HOSTNAME=appleid.yourdomain.com

# 5. 商业化跳转店铺
STORE_URL=https://shop.yourdomain.com/item/appleid
```

---

## 三、Docker Compose 一键构建与启动

生产编排文件 `docker-compose.yml` 已经内置了安全降权、只读文件系统、tmpfs 挂载与健康检查：

```bash
# 1. 构建并后台启动容器
docker compose up -d --build

# 2. 查看容器运行状态与健康检查
docker compose ps

# 正常输出示例：
# NAME                          IMAGE                       STATUS
# appleid-autoshare-redis-1     redis:7.4-alpine            Up (healthy)
# appleid-autoshare-app-1       appleid-autoshare-app       Up (healthy)
```

### 服务健康验证
```bash
# 验证健康探测端点
curl -fsS http://127.0.0.1:18740/healthz
# 期望返回: {"status":"ok"}

curl -fsS http://127.0.0.1:18740/readyz
# 期望返回: {"status":"ready"}
```

---

## 四、Nginx / 反向代理配置（带 SSL）

在你的服务器 Nginx 或宝塔面板中，为站点添加如下反向代理配置：

```nginx
server {
    listen 80;
    server_name appleid.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name appleid.yourdomain.com;

    # SSL 证书配置
    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 安全头与反代头透传
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # 关键静态资源协商缓存（杜绝旧缓存导致样式错乱）
    location ~* \.(?:css|js)$ {
        proxy_pass http://127.0.0.1:18740;
        add_header Cache-Control "no-cache, must-revalidate";
        proxy_set_header Host $host;
    }

    # 主应用反向代理
    location / {
        proxy_pass http://127.0.0.1:18740;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        # 超时设置
        proxy_connect_timeout 15s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```

---

## 五、日常维护与更新升级

### 1. 代码更新与无缝重启
当后续仓库有更新提交时，仅需两步即可平滑升级：
```bash
cd /data/appleid-autoshare
git pull origin experiment/discord-colorway
docker compose up -d --build app
```

### 2. 查看日志与排错
```bash
# 查看实时运行日志
docker compose logs -f app

# 查看最近 100 行日志
docker compose logs --tail=100 app
```

### 3. 本地全套测试回归（可选）
如果生产方需要在宿主机运行代码级校验：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

pytest -q
ruff check app main.py tests
mypy app main.py
```
全部 123 项测试通过后即可放心交付。
