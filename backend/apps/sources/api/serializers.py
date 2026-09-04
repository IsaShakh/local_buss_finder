from rest_framework import serializers

from apps.sources.models import Source


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = (
            "id",
            "code",
            "name",
            "source_type",
            "is_paid",
            "is_active",
            "attribution",
            "license_code",
            "requests_per_second",
            "concurrency",
            "timeout_seconds",
            "max_retries",
        )
        read_only_fields = fields
