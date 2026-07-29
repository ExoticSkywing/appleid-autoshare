# Apple ID AutoShare 🍎

> 全网高质量 Apple ID 自动化聚合、清洗与高可用 API 共享引擎。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-brightgreen.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)

## 🌟 特性

- 🤖 **自动化采集与去重**：自动聚合上游优质数据源（如 dabaoid / appstore.autos 等），毫秒级去重清洗。
- ⚡ **高性能 RESTful API**：原生 FastAPI 异步支持，开箱即用。
- 🛡️ **质量智能过滤**：自动剔除已锁定、异常账号，仅向终端输出正常可用账号。
- 🐳 **Docker 极速部署**：提供 Docker 和 Docker Compose 一键启动文件。

## 🚀 快速开始

### 使用 Docker 部署 (推荐)

```bash
docker-compose up -d --build
```

系统将在 `http://localhost:8000` 启动服务。

### 手动运行

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 📡 API 接口文档

### 1. 获取可用账号列表

- **Endpoint**: `GET /api/v1/accounts`
- **Query Params**:
  - `region`: (可选) 筛选地区，例如 `美国`、`台湾`
  - `status`: (可选) 状态，默认 `normal`
- **Response**:

```json
{
  "code": 200,
  "msg": "success",
  "total": 9,
  "last_updated": "2026-07-30 00:30:00",
  "data": [
    {
      "username": "BeyerleinLemoyne99@outlook.com",
      "password": "xxxxxxxx",
      "region": "美国",
      "status": "normal",
      "status_text": "正常",
      "last_check": "2026-07-30 00:24:45",
      "source": "dabaoid"
    }
  ]
}
```

### 2. 系统统计信息

- **Endpoint**: `GET /api/v1/stats`

---

## 📄 开源协议

MIT License
