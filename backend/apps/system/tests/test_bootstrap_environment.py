from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.geography.models import SearchArea
from apps.sources.models import Source
from apps.taxonomy.models import BusinessCategory, SourceCategoryMapping


@pytest.mark.django_db(transaction=True)
@override_settings(DISCOVERY_USE_FIXTURES=True, E2E_FIXTURE_CREDENTIALS=True)
def test_bootstrap_is_idempotent_and_creates_fixture_owner(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "owner")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "e2e-password")
    output = StringIO()

    call_command("bootstrap_environment", "--require-owner", stdout=output)
    first_counts = (
        SearchArea.objects.count(),
        Source.objects.count(),
        BusinessCategory.objects.count(),
        SourceCategoryMapping.objects.count(),
    )
    call_command("bootstrap_environment", "--require-owner", stdout=output)

    user = get_user_model().objects.get(username="owner")
    assert get_user_model().objects.filter(username="owner").count() == 1
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("e2e-password")
    assert first_counts == (1, 2, 8, 8)
    assert (
        SearchArea.objects.count(),
        Source.objects.count(),
        BusinessCategory.objects.count(),
        SourceCategoryMapping.objects.count(),
    ) == first_counts
    assert "e2e-password" not in output.getvalue()


@pytest.mark.django_db(transaction=True)
@override_settings(DISCOVERY_USE_FIXTURES=False, E2E_FIXTURE_CREDENTIALS=False)
def test_bootstrap_rejects_fixture_password_outside_fixture_mode(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "owner")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "e2e-password")

    with pytest.raises(CommandError, match="fixture-only"):
        call_command("bootstrap_environment", "--require-owner")

    assert SearchArea.objects.count() == 0
    assert Source.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_bootstrap_requires_both_owner_environment_variables(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="DJANGO_SUPERUSER_USERNAME"):
        call_command("bootstrap_environment", "--require-owner")

    assert SearchArea.objects.count() == 0
    assert Source.objects.count() == 0
