from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models

from apps.sources.models import Source
from common.models import TimestampedUUIDModel


class BusinessCategory(TimestampedUUIDModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent_id")),
                name="taxonomy_category_not_self_parent",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.parent_id is None:
            return
        if self.parent_id == self.id:
            raise ValidationError({"parent": "Категория не может быть своим родителем."})

        visited = {self.id}
        ancestor_id = self.parent_id
        while ancestor_id is not None:
            if ancestor_id in visited:
                raise ValidationError({"parent": "Иерархия категорий содержит цикл."})
            visited.add(ancestor_id)
            ancestor_id = (
                BusinessCategory.objects.filter(id=ancestor_id)
                .values_list("parent_id", flat=True)
                .first()
            )


class SourceCategoryMapping(TimestampedUUIDModel):
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="category_mappings",
    )
    external_category = models.CharField(max_length=255)
    category = models.ForeignKey(
        BusinessCategory,
        on_delete=models.CASCADE,
        related_name="source_mappings",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("source_id", "external_category")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("source", "external_category"),
                name="taxonomy_mapping_source_external_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source.code}: {self.external_category}"
