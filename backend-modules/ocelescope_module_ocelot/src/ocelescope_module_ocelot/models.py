from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Literal, Optional


@dataclass
class OcelEntity:
    id: str
    attributes: dict[str, Any]
    relations: dict[str, List[str]]
    timestamp: Optional[datetime] = None


@dataclass
class PaginatedResponse:
    page: int
    page_size: int
    total_pages: int
    total_items: int
    items: List[OcelEntity]


@dataclass
class EntityTableColumn:
    accessor: str
    type: Literal["attribute", "relation"]
    title: str | None = None
