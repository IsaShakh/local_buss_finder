from django.http import JsonResponse


def csrf_failure(request, reason=""):
    return JsonResponse(
        {
            "error": {
                "code": "CSRF_FAILED",
                "detail": "Проверка CSRF не пройдена.",
                "fields": {},
            }
        },
        status=403,
    )
