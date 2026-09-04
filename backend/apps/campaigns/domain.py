from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CreateCampaignCommand:
    name: str
    search_area_id: UUID
    source_ids: tuple[UUID, ...]
    category_ids: tuple[UUID, ...]


class CampaignValidationError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        fields: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.fields = fields or {}
