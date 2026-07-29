import logging
import httpx
from typing import List, Dict, Any
from app.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

class AppstoreAutosAdapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "appstore_autos"

    def parse_json(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        accounts = []
        for acc in data.get("accounts", []):
            is_ok = acc.get("status") and acc.get("message") == "正常"
            accounts.append({
                "username": acc.get("username", "").strip(),
                "password": acc.get("password", "").strip(),
                "region": acc.get("region_display", "").strip(),
                "status": "normal" if is_ok else "error",
                "status_text": "正常" if is_ok else acc.get("message", "异常"),
                "last_check": acc.get("last_check", ""),
                "source": self.source_name
            })
        return accounts

    async def fetch_accounts(self) -> List[Dict[str, Any]]:
        url = "https://appstore.autos/shareapi/xxyunAPP"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return self.parse_json(res.json())
        except Exception as e:
            logger.error(f"Error fetching appstore_autos: {e}")
        return []
