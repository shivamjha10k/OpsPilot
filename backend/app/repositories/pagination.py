from dataclasses import dataclass
from math import ceil
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PageResult(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return ceil(self.total / self.page_size) if self.total else 0


def pagination_window(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise ValueError("page must be greater than zero")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    return (page - 1) * page_size, page_size
