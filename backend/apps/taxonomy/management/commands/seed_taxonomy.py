from typing import ClassVar

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.sources.models import Source
from apps.taxonomy.models import BusinessCategory, SourceCategoryMapping


class Command(BaseCommand):
    help = "Создаёт базовую бизнес-таксономию и mappings источников."

    category_tree: ClassVar[tuple[tuple[str, str, str, str], ...]] = (
        ("health", "Медицина", "dentist", "Стоматология"),
        (
            "real-estate",
            "Недвижимость",
            "real-estate-agency",
            "Агентство недвижимости",
        ),
        ("hospitality", "Гостеприимство", "hotel", "Отель"),
        ("beauty", "Красота", "beauty-salon", "Салон красоты"),
    )
    provider_mappings: ClassVar[dict[str, tuple[tuple[str, str], ...]]] = {
        "overture": (
            ("dentist", "dentist"),
            ("real_estate_agent", "real-estate-agency"),
            ("hotel", "hotel"),
            ("beauty_salon", "beauty-salon"),
        ),
        "osm": (
            ("amenity=dentist", "dentist"),
            ("office=estate_agent", "real-estate-agency"),
            ("tourism=hotel", "hotel"),
            ("shop=beauty", "beauty-salon"),
        ),
    }

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        sources = Source.objects.in_bulk(self.provider_mappings, field_name="code")
        missing_sources = sorted(set(self.provider_mappings) - set(sources))
        if missing_sources:
            raise CommandError(
                "Сначала выполните seed_sources; отсутствуют источники: "
                + ", ".join(missing_sources)
            )

        categories: dict[str, BusinessCategory] = {}
        for root_slug, root_name, leaf_slug, leaf_name in self.category_tree:
            root = self._upsert_category(slug=root_slug, name=root_name, parent=None)
            leaf = self._upsert_category(slug=leaf_slug, name=leaf_name, parent=root)
            categories[root_slug] = root
            categories[leaf_slug] = leaf

        for source_code, mappings in self.provider_mappings.items():
            source = sources[source_code]
            for external_category, category_slug in mappings:
                self._upsert_mapping(
                    source=source,
                    external_category=external_category,
                    category=categories[category_slug],
                )

        self.stdout.write(self.style.SUCCESS("Бизнес-таксономия актуализирована."))

    @staticmethod
    def _upsert_category(
        *,
        slug: str,
        name: str,
        parent: BusinessCategory | None,
    ) -> BusinessCategory:
        category = BusinessCategory.objects.filter(slug=slug).first()
        if category is None:
            category = BusinessCategory(slug=slug, is_active=True)
        category.name = name
        category.parent = parent
        category.full_clean()
        category.save()
        return category

    @staticmethod
    def _upsert_mapping(
        *,
        source: Source,
        external_category: str,
        category: BusinessCategory,
    ) -> SourceCategoryMapping:
        mapping = SourceCategoryMapping.objects.filter(
            source=source,
            external_category=external_category,
        ).first()
        if mapping is None:
            mapping = SourceCategoryMapping(
                source=source,
                external_category=external_category,
                is_active=True,
            )
        mapping.category = category
        mapping.full_clean()
        mapping.save()
        return mapping
