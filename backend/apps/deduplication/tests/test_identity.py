from uuid import uuid4

import pytest

from apps.deduplication.identity import extract_official_domains
from apps.deduplication.scoring import category_relation


@pytest.mark.parametrize(
    ("websites", "expected"),
    [
        (("HTTPS://WWW.Example.COM/Services",), ("example.com",)),
        (("https://Example.com:8443/path",), ("example.com",)),
        (
            ("https://example.com/one", "http://www.example.com/two", "https://EXAMPLE.COM"),
            ("example.com",),
        ),
        (("not a url", "ftp://example.com", "https:///missing-host"), ()),
        (("https://www.instagram.com/example", "https://facebook.com/example"), ()),
        (
            (
                "https://booking.com/hotel/example",
                "https://www.tripadvisor.com/Restaurant_Review",
                "https://yelp.com/biz/example",
            ),
            (),
        ),
    ],
)
def test_extract_official_domains_normalizes_only_matchable_hosts(websites, expected):
    """Catches accepting social/directory hosts or retaining URL presentation details."""
    assert extract_official_domains(websites) == expected


def test_extract_official_domains_does_not_mutate_contact_values():
    """Catches an extractor that modifies the contacts it only needs to inspect."""
    websites = ["HTTPS://WWW.Example.COM/Services", "https://instagram.com/example"]

    assert extract_official_domains(websites) == ("example.com",)
    assert websites == ["HTTPS://WWW.Example.COM/Services", "https://instagram.com/example"]


def test_category_relation_uses_ids_without_database_access():
    """Catches category compatibility that mishandles missing, equal, or unequal IDs."""
    category_id = uuid4()

    assert category_relation(None, None) == "neutral"
    assert category_relation(category_id, None) == "neutral"
    assert category_relation(category_id, category_id) == "same"
    assert category_relation(category_id, uuid4()) == "incompatible"
