from collections.abc import Collection
from uuid import UUID

from apps.taxonomy.models import SourceCategoryMapping


def resolve_category(source_id: UUID, external_category: str) -> UUID | None:
    return (
        SourceCategoryMapping.objects.filter(
            source_id=source_id,
            source__is_active=True,
            external_category=external_category,
            category__is_active=True,
            is_active=True,
        )
        .values_list("category_id", flat=True)
        .first()
    )


def resolve_external_categories(
    source_id: UUID,
    category_ids: Collection[UUID],
) -> tuple[str, ...]:
    mappings = SourceCategoryMapping.objects.filter(
        source_id=source_id,
        source__is_active=True,
        category__is_active=True,
        is_active=True,
    )
    if category_ids:
        mappings = mappings.filter(category_id__in=category_ids)

    return tuple(sorted(set(mappings.values_list("external_category", flat=True))))
