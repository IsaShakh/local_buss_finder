from django.core.management.base import BaseCommand
from django.db import transaction

from apps.geography.models import Country, District, Province, SearchArea
from apps.geography.services import ALANYA_PILOT_BBOX, multipolygon_from_bbox


class Command(BaseCommand):
    help = "Создаёт базовую географию Türkiye → Antalya → Alanya."

    @transaction.atomic
    def handle(self, *args, **options):
        country, _ = Country.objects.update_or_create(
            code="TR",
            defaults={"name": "Türkiye", "name_ru": "Турция"},
        )
        province, _ = Province.objects.update_or_create(
            country=country,
            code="07",
            defaults={"name": "Antalya", "name_ru": "Анталья"},
        )
        district, _ = District.objects.update_or_create(
            province=province,
            slug="alanya",
            defaults={"name": "Alanya", "name_ru": "Аланья"},
        )

        area = SearchArea.objects.filter(name="Аланья — пилот").first()
        if area is None:
            area = SearchArea(name="Аланья — пилот", country=country)
        area.country = country
        area.province = province
        area.district = district
        area.neighborhood = None
        area.geometry = multipolygon_from_bbox(ALANYA_PILOT_BBOX)
        area.is_active = True
        area.full_clean()
        area.save()

        self.stdout.write(self.style.SUCCESS("Географические справочники готовы."))
