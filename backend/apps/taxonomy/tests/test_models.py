import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.taxonomy.models import BusinessCategory


@pytest.mark.django_db
def test_category_slug_is_unique():
    BusinessCategory.objects.create(name="Медицина", slug="health")

    with pytest.raises(IntegrityError), transaction.atomic():
        BusinessCategory.objects.create(name="Другая медицина", slug="health")


@pytest.mark.django_db
def test_category_rejects_self_parent():
    category = BusinessCategory.objects.create(name="Медицина", slug="health")
    category.parent = category

    with pytest.raises(ValidationError, match="своим родителем"):
        category.full_clean()


@pytest.mark.django_db
def test_category_rejects_longer_cycle():
    first = BusinessCategory.objects.create(name="Первая", slug="first")
    second = BusinessCategory.objects.create(name="Вторая", slug="second", parent=first)
    first.parent = second

    with pytest.raises(ValidationError, match="цикл"):
        first.full_clean()


@pytest.mark.django_db(transaction=True)
def test_database_rejects_self_parent():
    category = BusinessCategory.objects.create(name="Медицина", slug="health")

    with pytest.raises(IntegrityError), transaction.atomic():
        BusinessCategory.objects.filter(pk=category.pk).update(parent_id=category.pk)
