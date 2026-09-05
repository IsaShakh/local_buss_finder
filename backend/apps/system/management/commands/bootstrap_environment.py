import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError, call_command

FIXTURE_PASSWORD = "e2e-password"


class Command(BaseCommand):
    help = "Применяет migrations, загружает справочники и создаёт локального владельца."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--require-owner",
            action="store_true",
            help="Завершиться с ошибкой, если credentials владельца не переданы.",
        )

    def handle(self, *args, **options) -> None:
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        credentials_complete = bool(username and password)

        if bool(username) != bool(password):
            raise CommandError(
                "DJANGO_SUPERUSER_USERNAME и DJANGO_SUPERUSER_PASSWORD должны быть заданы вместе."
            )
        if options["require_owner"] and not credentials_complete:
            raise CommandError("DJANGO_SUPERUSER_USERNAME и DJANGO_SUPERUSER_PASSWORD обязательны.")
        if password == FIXTURE_PASSWORD and not (
            getattr(settings, "DISCOVERY_USE_FIXTURES", False)
            and getattr(settings, "E2E_FIXTURE_CREDENTIALS", False)
        ):
            raise CommandError("fixture-only password разрешён только в изолированном E2E режиме.")

        verbosity = options["verbosity"]
        call_command(
            "migrate",
            interactive=False,
            verbosity=verbosity,
            stdout=self.stdout,
        )
        for command_name in ("seed_reference_data", "seed_sources", "seed_taxonomy"):
            call_command(command_name, verbosity=verbosity, stdout=self.stdout)

        if credentials_complete:
            user_model = get_user_model()
            user, _ = user_model.objects.get_or_create(username=username)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Владелец {username} готов."))

        self.stdout.write(self.style.SUCCESS("Окружение готово."))
