class DiscoveryError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


class TransientSourceError(DiscoveryError):
    pass


class RateLimitedSourceError(TransientSourceError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("SOURCE_RATE_LIMITED")


class PermanentSourceError(DiscoveryError):
    pass


class InvalidSourcePayload(PermanentSourceError):
    def __init__(self, detail: str = "") -> None:
        super().__init__("INVALID_SOURCE_PAYLOAD", detail)


class UnknownDiscoveryAdapter(PermanentSourceError):
    def __init__(self, source_code: str) -> None:
        self.source_code = source_code
        super().__init__("UNKNOWN_DISCOVERY_ADAPTER", source_code)
