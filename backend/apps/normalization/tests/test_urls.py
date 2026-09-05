import pytest

from apps.normalization.rules.urls import InvalidUrl, normalize_url


def test_url_normalizes_host_and_removes_fragment_without_dropping_path_query():
    assert normalize_url("HTTPS://Example.COM/hizmet?x=1#team") == "https://example.com/hizmet?x=1"


@pytest.mark.parametrize("value", ["ftp://example.com", "example.com", "https:///missing-host"])
def test_url_rejects_non_http_or_missing_host(value):
    with pytest.raises(InvalidUrl):
        normalize_url(value)
