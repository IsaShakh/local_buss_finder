from typing import ClassVar

from django.contrib.postgres.operations import CreateExtension, TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    operations: ClassVar = [
        CreateExtension("postgis"),
        TrigramExtension(),
        UnaccentExtension(),
    ]
