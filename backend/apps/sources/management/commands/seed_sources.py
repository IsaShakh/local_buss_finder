from decimal import Decimal
from typing import Any, ClassVar

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.models import Source


class Command(BaseCommand):
    help = "Создаёт или обновляет конфигурацию источников discovery."

    source_defaults: ClassVar[dict[str, dict[str, Any]]] = {
        "overture": {
            "name": "Overture Maps",
            "source_type": Source.Type.OPEN_DATA,
            "attribution": "Overture Maps Foundation, overturemaps.org",
            "license_code": "CDLA-Permissive-2.0/Apache-2.0",
            "is_paid": False,
            "requests_per_second": Decimal("1.00"),
            "concurrency": 1,
            "timeout_seconds": 60,
            "max_retries": 3,
        },
        "osm": {
            "name": "OpenStreetMap",
            "source_type": Source.Type.OPEN_DATA,
            "attribution": "© OpenStreetMap contributors",
            "license_code": "ODbL-1.0",
            "is_paid": False,
            "requests_per_second": Decimal("0.20"),
            "concurrency": 1,
            "timeout_seconds": 60,
            "max_retries": 3,
        },
    }

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset-active",
            action="store_true",
            help="Вернуть источники в активное состояние.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        for code, defaults in self.source_defaults.items():
            source = Source.objects.filter(code=code).first()
            if source is None:
                source = Source(code=code, is_active=True)

            for field, value in defaults.items():
                setattr(source, field, value)

            if options["reset_active"]:
                source.is_active = True

            source.full_clean()
            source.save()

        self.stdout.write(self.style.SUCCESS("Источники discovery актуализированы."))
