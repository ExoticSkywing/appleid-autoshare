import re
import logging
import httpx
from typing import List, Dict, Any
from app.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

class DabaoidAdapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "dabaoid"

    def parse_html(self, html: str) -> List[Dict[str, Any]]:
        accounts = []
        cards = html.split('<div class="col-xs-3 col-md-3">')
        for card in cards[1:]:
            user_match = re.search(r'id="username_\d+"[^>]*data-clipboard-text="([^"]+)"', card)
            pass_match = re.search(r'id="password_\d+"[^>]*data-clipboard-text="([^"]+)"', card)
            region_match = re.search(r'<span class="badge bg-indigo text-indigo-fg">([^<]+)</span>', card)
            status_match = re.search(r'状态:[^<]*<span[^>]*>([^<]+)</span>', card)
            check_match = re.search(r'上次检查:\s*([^<]+)', card)

            if user_match and pass_match:
                status_text = status_match.group(1).strip() if status_match else "未知"
                accounts.append({
                    "username": user_match.group(1).strip(),
                    "password": pass_match.group(1).strip(),
                    "region": region_match.group(1).strip() if region_match else "未知",
                    "status": "normal" if "正常" in status_text else "error",
                    "status_text": status_text,
                    "last_check": check_match.group(1).strip() if check_match else "",
                    "source": self.source_name
                })
        return accounts

    async def fetch_accounts(self) -> List[Dict[str, Any]]:
        url = "https://id.dabaoid.top/share/vjBrzNCdmZ"
        headers = {
            "Referer": "https://id.qingfeng888.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return self.parse_html(res.text)
        except Exception as e:
            logger.error(f"Error fetching dabaoid: {e}")
        return []
