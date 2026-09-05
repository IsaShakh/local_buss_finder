from time import perf_counter

from common.observability import safe_correlation_id, structured_event


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = perf_counter()
        correlation_id = safe_correlation_id(request.headers.get("X-Correlation-ID"))
        request.correlation_id = correlation_id
        response = self.get_response(request)
        response["X-Correlation-ID"] = correlation_id
        structured_event(
            "http.request.completed",
            request_id=correlation_id,
            correlation_id=correlation_id,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
            message="HTTP request completed",
        )
        return response
