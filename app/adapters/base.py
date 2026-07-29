from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    async def fetch_accounts(self) -> List[Dict[str, Any]]:
        pass
