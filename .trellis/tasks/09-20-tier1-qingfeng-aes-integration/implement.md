# Tier-1 清风 (Qingfeng Dabaoid) 实施交接计划 (Implementation Plan)

> 本任务供后端开发同事对接使用。

## 1. 实施清单

### 阶段一：配置与环境对接
- [x] 在 `app/config.py` 中添加 `SOURCE_QINGFENG_ENABLED`、运行时注入的 `SOURCE_QINGFENG_URL`、`SOURCE_QINGFENG_REFERER`、`SOURCE_QINGFENG_POLL_SECONDS`，且默认禁用并避免在仓库内写入端点。
- [x] 在 `.env.example` 中补充相应配置项与注释说明。

### 阶段二：适配器开发 (`QingfengAesAdapter`)
- [x] 在 `app/adapters/` 目录下新增 `qingfeng_aes.py`。
- [x] 实现 Referer 请求头注入与通用浏览器请求头。
- [x] 实现原生 Python 版 Dean Edwards/custom Packer 有界解包，并提取唯一 32 位 Hex 种子。
- [x] 实现基于 `cryptography` 的 AES-CBC-Pkcs7 动态解密核心算法。
- [x] 提取并清洗状态标记为“正常”且包含明确“已解锁小火箭”肯定标识的账号对。

### 阶段三：聚合器注册与测试
- [x] 在聚合器构建流程中注册 `QingfengAesAdapter`。
- [x] 编写 Mock 单元测试 `tests/test_qingfeng_aes_adapter.py`，验证包含 AES 加密 HTML 样本的解密正确性。
- [x] 验证 Referer 拒绝、密码密文损坏、解密失败、冲突状态、否定购买、跨卡配对和多种子时 fail-closed。

### 阶段四：集成验证
- [x] 启动本地轮询，验证解密后的账号进入独立 `qingfeng` Redis slice。
- [ ] 通过前端分发接口人工验证下发账号能在目标区域商店登录并下载目标应用；不得在任务记录中保存凭据或截图。
