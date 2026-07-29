from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
from app.services.aggregator import AccountAggregator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="Apple ID AutoShare API",
    description="High-availability, automated Apple ID aggregator and distribution system.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

aggregator = AccountAggregator()
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    await aggregator.refresh()
    scheduler.add_job(aggregator.refresh, "interval", minutes=5)
    scheduler.start()

@app.get("/api/v1/accounts")
async def get_accounts(
    region: str = Query(None, description="Filter by region (e.g. 美国, 台湾)"),
    status: str = Query("normal", description="Filter by status ('normal' or 'all')")
):
    cache = aggregator.cache
    accounts = cache["accounts"]
    
    if status == "normal":
        accounts = [a for a in accounts if a["status"] == "normal"]
    if region:
        accounts = [a for a in accounts if region.lower() in a["region"].lower()]
        
    return JSONResponse(content={
        "code": 200,
        "msg": "success",
        "total": len(accounts),
        "last_updated": cache["last_updated"],
        "sources_stat": cache["sources_stat"],
        "data": accounts
    })

@app.get("/api/v1/stats")
async def get_stats():
    cache = aggregator.cache
    return JSONResponse(content={
        "code": 200,
        "total_accounts": len(cache["accounts"]),
        "valid_accounts": len([a for a in cache["accounts"] if a["status"] == "normal"]),
        "last_updated": cache["last_updated"],
        "sources": cache["sources_stat"]
    })

@app.get("/", response_class=HTMLResponse)
async def home_page():
    html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apple ID AutoShare - 高可用苹果ID共享中心</title>
    <style>
        :root { --primary: #0071e3; --bg: #f5f5f7; --card-bg: #ffffff; --text: #1d1d1f; }
        body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 30px; }
        h1 { font-size: 2.2rem; margin-bottom: 8px; }
        p.subtitle { color: #86868b; }
        .warning-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-size: 0.95rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        .card { background: var(--card-bg); border-radius: 14px; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .badge { background: #e8f2ff; color: var(--primary); padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; }
        .field { margin-top: 12px; }
        .label { font-size: 0.8rem; color: #86868b; }
        .value-box { display: flex; justify-content: space-between; align-items: center; background: #f5f5f7; padding: 8px 12px; border-radius: 8px; margin-top: 4px; font-family: monospace; }
        .copy-btn { background: var(--primary); color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
        .copy-btn:hover { opacity: 0.9; }
        footer { text-align: center; margin-top: 40px; color: #86868b; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🍎 Apple ID AutoShare</h1>
            <p class="subtitle">全网高质量免费苹果ID实时共享平台</p>
        </header>

        <div class="warning-box">
            ⚠️ <strong>严格提示：</strong>请务必仅在 <strong>App Store</strong> 中登录下载应用，<strong>严禁在系统设置 (iCloud) 中登录</strong>，以免造成设备被锁定！
        </div>

        <div class="grid" id="accountGrid">加载中...</div>

        <footer>
            <p>© 2026 Apple ID AutoShare API Hub · 自动提取/高可用清洗引擎</p>
        </footer>
    </div>

    <script>
        async function loadAccounts() {
            const res = await fetch('/api/v1/accounts?status=normal');
            const data = await res.json();
            const container = document.getElementById('accountGrid');
            
            if (!data.data || data.data.length === 0) {
                container.innerHTML = '<p>暂无可用账号，请稍后刷新。</p>';
                return;
            }

            container.innerHTML = data.data.map(acc => `
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="badge">${acc.region || '美区'}</span>
                        <span style="color:#34c759; font-size:0.85rem;">● ${acc.status_text}</span>
                    </div>
                    <div class="field">
                        <div class="label">账号 (Apple ID)</div>
                        <div class="value-box">
                            <span>${acc.username}</span>
                            <button class="copy-btn" onclick="copy('${acc.username}')">复制</button>
                        </div>
                    </div>
                    <div class="field">
                        <div class="label">密码</div>
                        <div class="value-box">
                            <span>${acc.password}</span>
                            <button class="copy-btn" onclick="copy('${acc.password}')">复制</button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function copy(text) {
            navigator.clipboard.writeText(text);
            alert('已复制到剪贴板！');
        }

        loadAccounts();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
