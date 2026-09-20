# Tier-1 清风 (Qingfeng Dabaoid) 核心小火箭源接入需求 (PRD)

## 1. 业务目标与来源定位

### 1.1 业务背景
在近期对全网 Apple ID 共享源的实测中，公共免鉴权源多发生业务漂移（如 `SRC-APPSTORE-AUTOS` 转为仅提供 Nextin 客户端）。
经授权的协议逆向与实测确认，该来源可作为 Tier-1 加密 HTML 账号来源。生产端点与防盗链来源均作为运行时秘密注入，不写入仓库。

### 1.2 来源定位与等级
- **来源标识**: `SRC-QINGFENG-AES`
- **来源等级**: **Tier-1 核心主力源** (Core Primary Source for Shadowrocket)
- **目标端点**: 由 `SOURCE_QINGFENG_URL` 在运行时注入；防盗链来源由 `SOURCE_QINGFENG_REFERER` 注入
- **协议模式**: **Mode 3.5 (Referer Bypass + JS Dynamic AES Decryption)**

---

## 2. 核心功能与安全业务要求

### 2.1 请求与防盗链伪装
1. 请求必须携带合法的浏览器指纹 Header，且必须包含固定防盗链头：
   ```http
   Referer: <runtime SOURCE_QINGFENG_REFERER>
   ```
2. 禁止直连访问（直连会被源站 Nginx / ThinkPHP 拦截并返回 403 域名限制）。

### 2.2 传输层 AES 动态解密逆向要求
源站为了防止简单爬虫，对 HTML 中的密码字段进行了 AES 加密存储在 `data-clipboard-text` 中，并内嵌混淆 JS 动态解密：
1. **混淆脚本提取**: 解析 HTML 中包含 `eval(function(h,u,n,t,e,r)...)` 的 JS 代码块。
2. **密钥派生算法**:
   - 从解包后的 JS 逻辑中提取唯一的 32 位 Hex 种子；缺失或歧义时 fail-closed。
   - 计算种子字符串的 `SHA256` 哈希值作为 AES 密钥 Hex (`keyHex`)。
   - 取 `keyHex` 前 16 字节作为 IV 向量。
3. **AES-128/256-CBC 解密**:
   - 模式: `CBC`
   - 填充: `Pkcs7`
   - 密文: 从目标卡片密码按钮节点 `data-clipboard-text` 提取的 Base64 字符串。
   - 产物: 解密出的 UTF-8 明文密码。

### 2.3 状态校验与数据清洗
1. **健康状态过滤**: 必须匹配卡片内 `状态: 正常` 或 `is-ready` 徽标，同时必须包含 `美区已解锁小火箭` 或类似正常已购标识。
2. **上游绝密隔离 (Zero-Leak)**:
   - 抹除所有“清风”、“dabaoid”等品牌标记、教程链接及源站备注。
   - 转换为系统通用 DTO 下发给 Redis 热号池。

---

## 3. 验收标准 (Acceptance Criteria)

- [x] 后端 Adapter 携带运行时 Referer 能够稳定获取源站 HTML。
- [x] 能够全自动完成安全 Packer 解包与 AES 解密，并写入独立短时 Slice。
- [ ] 由授权人员人工确认下发账号可在目标区域商店登录并下载目标应用；验收记录不得包含凭据或截图。
- [x] 后台轮询可同步轮换后的密文和动态种子；失败轮次不覆盖或续期旧 Slice。
