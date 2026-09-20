# Tier-1 清风 (Qingfeng Dabaoid) 接入技术设计 (Technical Design)

## 1. 架构组件与数据流拓扑

```text
┌────────────────────────────────────────────────────────┐
│             External Target Upstream (Tier-1)          │
│       Runtime SOURCE_QINGFENG_URL (secret)             │
│       Runtime SOURCE_QINGFENG_REFERER (secret)         │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP GET (with Spoofed Headers)
                           ▼
┌────────────────────────────────────────────────────────┐
│      QingfengAesAdapter (app/adapters/qingfeng_aes.py) │
│                                                        │
│  1. DOM Extraction:                                    │
│     - Extract Card List (Username + Encrypted Password)│
│     - Extract Packed JS Block (eval packer)            │
│  2. Key & Crypto Engine (Python Native / cryptography): │
│     - Unpack Dean Edwards Packer                       │
│     - Regex Seed Key -> SHA256 -> Key & IV             │
│     - AES-CBC-Pkcs7 Decrypt (Base64 Ciphertext)        │
│  3. Sanitizer & DTO Normalizer                         │
└──────────────────────────┬─────────────────────────────┘
                           │ Standardized CandidateAccount
                           ▼
┌────────────────────────────────────────────────────────┐
│                 Redis Ephemeral Slice                  │
│       Dedicated source slice (runtime prefix and TTL)   │
└────────────────────────────────────────────────────────┘
```

---

## 2. 核心逆向解密实现参考 (Python 算法规范)

后端同事可直接在 Python 中使用标准算法还原该解密链路，无需调用 Node.js 运行时：

```python
import hashlib
import base64
import re
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

def extract_seed_and_decrypt(html: str, encrypted_b64: str) -> str:
    # 1. 提取 Packer 参数并解包 (或直接正则匹配种子 key)
    # 解包后的代码应包含唯一的 CryptoJS.SHA256("<32-hex-seed>") 调用
    # 支持从 HTML/JS 中提取唯一 32 位 Hex 种子；多候选时 fail-closed:
    seed_match = re.search(r'CryptoJS\.SHA256\(["\x27]([a-fA-F0-9]{32})["\x27]\)', html)
    if not seed_match:
        # 兼容备用解包正则
        unpacked_code = unpack_packer(html)
        seed_match = re.search(r'CryptoJS\.SHA256\(["\x27]([a-fA-F0-9]{32})["\x27]\)', unpacked_code)

    seed_hex = seed_match.group(1)

    # 2. 派生 Key 和 IV
    # keyHex = sha256(seed_hex) -> 64 char hex string
    key_hash = hashlib.sha256(seed_hex.encode("utf-8")).hexdigest()
    # CryptoJS.enc.Hex.parse(keyHex) -> 32 bytes key
    key_bytes = bytes.fromhex(key_hash)
    # iv = key.words.slice(0, 4) -> key 前 16 字节
    iv_bytes = key_bytes[:16]

    # 3. AES-CBC 解密
    ciphertext = base64.b64decode(encrypted_b64)
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()

    # 4. PKCS7 去除 Padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_data) + unpadder.finalize()
    return plaintext.decode("utf-8")
```

---

## 3. 错误与异常处理状态机

| 场景 | 状态判定 | 处理动作 |
| :--- | :--- | :--- |
| **Referer 被拒 / 返回 403** | `HTTP 403` / 页面提示“已开启域名限制” | 记录 Warn 日志，该轮 Slice 标记失效，触发告警。 |
| **种子密钥漂移 / 正则匹配失败** | 无法解析到 32 位 Seed | 记录 Error 日志，不向 Redis 写入脏数据。 |
| **AES 解密 Padding 错误** | 解密异常 / 明文字符串为空 | 丢弃当前单条记录，保留其他有效解密项。 |
| **页面标记“维护/空池”** | 卡片中无有效正常账号 | 该源不产生账号，降级由其他 Tier-1/1.5 源兜底。 |
