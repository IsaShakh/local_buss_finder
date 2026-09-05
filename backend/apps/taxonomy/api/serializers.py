from rest_framework import serializers

from apps.taxonomy.models import BusinessCategory


class BusinessCategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = BusinessCategory
        fields = ("id", "name", "slug", "children")
        read_only_fields = fields

    def get_children(self, obj: BusinessCategory) -> list[dict]:
        children = obj.children.filter(is_active=True).order_by("name", "id")
        return BusinessCategorySerializer(
            children,
            many=True,
            context=self.context,
        ).data
