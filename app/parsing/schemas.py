from dataclasses import dataclass, field
from enum import Enum

class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"

@dataclass
class ExtractedAsset:
    asset_type: str
    minio_key: str
    public_url: str
    alt_text: str = ""
    source_ref: str = ""

@dataclass
class ParseResult:
    markdown: str
    markdown_key: str | None = None
    assets: list[ExtractedAsset] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)