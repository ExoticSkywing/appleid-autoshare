import logging
from typing import List, Dict, Any
from datetime import datetime
from app.adapters.dabaoid import DabaoidAdapter
from app.adapters.appstore_autos import AppstoreAutosAdapter

logger = logging.getLogger(__name__)

class AccountAggregator:
    def __init__(self):
        self.adapters = [DabaoidAdapter(), AppstoreAutosAdapter()]
        self.cache = {
            "last_updated": None,
            "accounts": [],
            "sources_stat": {}
        }

    async def refresh(self) -> Dict[str, Any]:
        logger.info("Aggregator starting refresh across all upstreams...")
        all_raw = []
        sources_stat = {}

        for adapter in self.adapters:
            accs = await adapter.fetch_accounts()
            sources_stat[adapter.source_name] = len(accs)
            all_raw.extend(accs)

        unique_map = {}
        for acc in all_raw:
            uname = acc["username"].lower()
            if uname not in unique_map or (unique_map[uname]["status"] != "normal" and acc["status"] == "normal"):
                unique_map[uname] = acc

        aggregated = list(unique_map.values())
        self.cache["accounts"] = aggregated
        self.cache["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cache["sources_stat"] = sources_stat

        logger.info(f"Aggregator refresh complete. Total unique accounts: {len(aggregated)}")
        return self.cache
