from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.discovery.domain import DiscoveryAdapter, DiscoveryRequest


def assert_adapter_contract(adapter: "DiscoveryAdapter", request: "DiscoveryRequest") -> None:
    assert adapter.source_code
    assert adapter.resolve_dataset_version()
    payloads = list(adapter.discover(request))
    assert payloads
    for source_payload in payloads:
        assert source_payload.external_id
        assert source_payload.provenance.dataset_version == request.dataset_version
        parsed = adapter.parse_payload(source_payload)
        assert parsed.external_id == source_payload.external_id
