from abc import ABC, abstractmethod
from app.parsing.schemas import ParseResult

class BaseParser(ABC):
    @abstractmethod
    async def parse(
        self,
        *,
        file_data: bytes,
        file_name: str,
        owner_id: int,
        doc_uuid: str,
        progress_callback=None,
    ) -> ParseResult:
        ...