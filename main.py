from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

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

# In-memory storage for aggregated accounts
CACHE = {
    "last_updated": None,
    "accounts": [],
    "sources_stat": {}
}

# --- ADAPTERS ---

async def fetch_dabaoid_accounts() -> List[Dict[str, Any]]:
    """Fetch accounts from qingfeng888 / dabaoid"""
    url = "https://id.dabaoid.top/share/vjBrzNCdmZ"
    headers = {
        "Referer": "https://id.qingfeng888.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    accounts = []
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                html = res.text
                cards = html.split('<div class="col-xs-3 col-md-3">')
                for card in cards[1:]:
                    user_match = re.search(r'id="username_\d+"[^>]*data-clipboard-text="([^"]+)"', card)
                    pass_match = re.search(r'id="password_\d+"[^>]*data-clipboard-text="([^"]+)"', card)
                    region_match = re.search(r'<span class="badge bg-indigo text-indigo-fg">([^<]+)</span>', card)
                    status_match = re.search(r'状态:[^<]*<span[^>]*>([^<]+)</span>', card)
                    check_match = re.search(r'上次检查:\s*([^<]+)', card)
                    
                    if user_match and pass_match:
                        accounts.append({
                            "username": user_match.group(1).strip(),
                            "password": pass_match.group(1).strip(),
                            "region": region_match.group(1).strip() if region_match else "未知",
                            "status": "normal" if (status_match and "正常" in status_match.group(1)) else "error",
                            "status_text": status_match.group(1).strip() if status_match else "未知",
                            "last_check": check_match.group(1).strip() if check_match else "",
                            "source": "dabaoid"
                        })
    except Exception as e:
        logging.error(f"Error fetching dabaoid accounts: {e}")
    return accounts

async def fetch_appstore_autos_accounts() -> List[Dict[str, Any]]:
    """Fetch accounts from appstore.autos API"""
    url = "https://appstore.autos/shareapi/xxyunAPP"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    accounts = []
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                for acc in data.get("accounts", []):
                    is_ok = acc.get("status") and acc.get("message") == "正常"
                    accounts.append({
                        "username": acc.get("username", "").strip(),
                        "password": acc.get("password", "").strip(),
                        "region": acc.get("region_display", "").strip(),
                        "status": "normal" if is_ok else "error",
                        "status_text": "正常" if is_ok else acc.get("message", "异常"),
                        "last_check": acc.get("last_check", ""),
                        "source": "appstore_autos"
                    })
    except Exception as e:
        logging.error(f"Error fetching appstore_autos accounts: {e}")
    return accounts

# --- AGGREGATION ENGINE ---

async def refresh_accounts_job():
    """Sync accounts from all upstreams and update in-memory cache"""
    logging.info("Starting background update job...")
    dabaoid_accs = await fetch_dabaoid_accounts()
    appstore_accs = await fetch_appstore_autos_accounts()
    
    all_raw = dabaoid_accs + appstore_accs
    
    # Deduplicate by username (case-insensitive)
    unique_map = {}
    sources_stat = {"dabaoid": len(dabaoid_accs), "appstore_autos": len(appstore_accs)}
    
    for acc in all_raw:
        uname = acc["username"].lower()
        # Keep normal status over error status if duplicated
        if uname not in unique_map or (unique_map[uname]["status"] != "normal" and acc["status"] == "normal"):
            unique_map[uname] = acc
            
    aggregated = list(unique_map.values())
    
    CACHE["accounts"] = aggregated
    CACHE["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CACHE["sources_stat"] = sources_stat
    logging.info(f"Update complete! Total unique accounts: {len(aggregated)}")

# --- SCHEDULER ---
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    await refresh_accounts_job()
    # Schedule every 5 minutes
    scheduler.add_job(refresh_accounts_job, "interval", minutes=5)
    scheduler.start()

# --- API ENDPOINTS ---

@app.get("/api/v1/accounts")
async def get_accounts(
    region: str = Query(None, description="Filter by region (e.g. 美国, 台湾)"),
    status: str = Query("normal", description="Filter by status ('normal' or 'all')")
):
    """Get aggregated Apple ID accounts"""
    accounts = CACHE["accounts"]
    
    if status == "normal":
        accounts = [a for a in accounts if a["status"] == "normal"]
    if region:
        accounts = [a for a in accounts if region.lower() in a["region"].lower()]
        
    return JSONResponse(content={
        "code": 200,
        "msg": "success",
        "total": len(accounts),
        "last_updated": CACHE["last_updated"],
        "sources_stat": CACHE["sources_stat"],
        "data": accounts
    })

@app.get("/api/v1/stats")
async def get_stats():
    """Get system statistics"""
    return JSONResponse(content={
        "code": 200,
        "total_accounts": len(CACHE["accounts"]),
        "valid_accounts": len([a for a in CACHE["accounts"] if a["status"] == "normal"]),
        "last_updated": CACHE["last_updated"],
        "sources": CACHE["sources_stat"]
    })

@app.get("/", response_class=HTMLResponse)
async def home_page():
    """Web Front-end Page"""
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
