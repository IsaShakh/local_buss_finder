from collections.abc import Mapping, Sequence
from typing import TypedDict

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler


class ApiErrorBody(TypedDict):
    code: str
    detail: str
    fields: dict[str, list[str]]


class ApiErrorResponse(TypedDict):
    error: ApiErrorBody


class ApiException(APIException):
    status_code = 400
    default_code = "API_ERROR"

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        status_code: int = 400,
        fields: dict[str, list[str]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.api_code = code
        self.fields = fields or {}
        super().__init__(detail=detail, code=code)


def _flatten_messages(value: object) -> list[str]:
    if isinstance(value, Mapping):
        return [
            message
            for nested_value in value.values()
            for message in _flatten_messages(nested_value)
        ]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [message for item in value for message in _flatten_messages(item)]
    return [str(value)]


def _validation_fields(detail: object) -> dict[str, list[str]]:
    if isinstance(detail, Mapping):
        return {str(field): _flatten_messages(messages) for field, messages in detail.items()}
    return {"non_field_errors": _flatten_messages(detail)}


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    fields: dict[str, list[str]] = {}
    if isinstance(exc, ApiException):
        code = exc.api_code
        detail = str(exc.detail)
        fields = exc.fields
    elif isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        detail = "Проверьте правильность заполнения полей."
        fields = _validation_fields(exc.detail)
    elif isinstance(exc, NotAuthenticated):
        code = "NOT_AUTHENTICATED"
        detail = "Требуется вход."
    elif isinstance(exc, AuthenticationFailed):
        code = "AUTHENTICATION_FAILED"
        detail = "Не удалось выполнить аутентификацию."
    elif isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        code = "PERMISSION_DENIED"
        detail = "Недостаточно прав."
    elif isinstance(exc, (NotFound, Http404)):
        code = "NOT_FOUND"
        detail = "Ресурс не найден."
    elif isinstance(exc, MethodNotAllowed):
        code = "METHOD_NOT_ALLOWED"
        detail = "Метод не разрешён."
    elif isinstance(exc, Throttled):
        code = "THROTTLED"
        detail = "Слишком много запросов."
    else:
        code = "API_ERROR"
        detail = str(getattr(exc, "detail", "Ошибка запроса."))

    payload: ApiErrorResponse = {
        "error": {
            "code": code,
            "detail": detail,
            "fields": fields,
        }
    }
    response.data = payload
    return response
