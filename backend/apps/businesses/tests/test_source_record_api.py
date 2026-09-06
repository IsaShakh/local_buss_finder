import json

import pytest

DETAIL_KEYS = {
    "id",
    "is_canonical",
    "campaign_id",
    "source_run_id",
    "source",
    "external_id",
    "source_dataset_version",
    "source_url",
    "attribution",
    "license_code",
    "raw",
    "payload",
    "normalization_status",
    "normalization_error_code",
    "parser_error_code",
    "fetched_at",
    "normalized",
}
RAW_KEYS = {
    "name",
    "category",
    "address",
    "phones",
    "emails",
    "websites",
    "social_urls",
    "location",
}
PAYLOAD_KEYS = {"key", "sha256", "bytes", "schema_version"}
NORMALIZED_KEYS = {
    "display_name",
    "normalized_name",
    "match_name",
    "category",
    "address_text",
    "country",
    "province",
    "district",
    "neighborhood",
    "location",
    "phones",
    "emails",
    "websites",
    "social_urls",
    "attributes",
    "warnings",
    "normalization_version",
    "normalized_at",
}


@pytest.mark.django_db
def test_source_record_list_is_paginated_and_explicitly_noncanonical(
    auth_client,
    normalized_records,
):
    response = auth_client.get("/api/v1/source-records/?page=1&page_size=2&ordering=display_name")

    assert response.status_code == 200
    assert response.json()["count"] == len(normalized_records)
    assert len(response.json()["results"]) == 2
    assert all(item["is_canonical"] is False for item in response.json()["results"])


@pytest.mark.django_db
def test_source_record_pagination_keeps_legacy_decimal_query_behavior(
    auth_client,
    normalized_records,
):
    malformed_page = auth_client.get("/api/v1/source-records/?page=1.0")
    legacy_default_size = auth_client.get("/api/v1/source-records/?page_size=1.0")
    integer_size = auth_client.get("/api/v1/source-records/?page_size=1")

    assert malformed_page.status_code == 404
    assert legacy_default_size.status_code == integer_size.status_code == 200
    assert len(legacy_default_size.json()["results"]) == 3
    assert len(integer_size.json()["results"]) == 1


@pytest.mark.django_db
def test_source_record_list_filters_campaign_source_category_and_search(
    auth_client,
    records,
):
    response = auth_client.get(
        f"/api/v1/source-records/?campaign={records.target.campaign_id}"
        f"&source=osm&category=dentist&search=smile"
    )

    assert [item["id"] for item in response.json()["results"]] == [str(records.target.id)]


@pytest.mark.django_db
def test_list_rejects_unsafe_query_and_never_leaks_non_normalized_rows(
    auth_client,
    records,
):
    too_large = auth_client.get("/api/v1/source-records/?page_size=101")
    unknown_filter = auth_client.get("/api/v1/source-records/?normalization_status=rejected")
    visible = auth_client.get("/api/v1/source-records/").json()["results"]

    assert too_large.status_code == 400
    assert unknown_filter.status_code == 400
    assert {item["id"] for item in visible}.isdisjoint(
        {str(records.rejected.id), str(records.failed.id), str(records.foreign.id)}
    )


@pytest.mark.django_db
def test_detail_shape_is_exact_and_contains_metadata_not_payload_body(auth_client, records):
    response = auth_client.get(f"/api/v1/source-records/{records.target.id}/")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == DETAIL_KEYS
    assert body["is_canonical"] is False
    assert set(body["source"]) == {"code", "name"}
    assert set(body["raw"]) == RAW_KEYS
    assert set(body["payload"]) == PAYLOAD_KEYS
    assert set(body["normalized"]) == NORMALIZED_KEYS
    assert set(body["normalized"]["country"]) == {"id", "name", "code"}
    assert set(body["normalized"]["district"]) == {"id", "name", "slug"}
    rendered = json.dumps(body)
    for forbidden in (
        "payload_body",
        "presigned_url",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
    ):
        assert forbidden not in rendered


@pytest.mark.django_db
@pytest.mark.parametrize("record_name", ["rejected", "failed"])
def test_owned_non_normalized_detail_is_visible_with_null_normalized(
    auth_client,
    records,
    record_name,
):
    record = getattr(records, record_name)

    response = auth_client.get(f"/api/v1/source-records/{record.id}/")

    assert response.status_code == 200
    assert response.json()["normalized"] is None
    assert response.json()["normalization_status"] == record_name


@pytest.mark.django_db
def test_foreign_and_missing_detail_are_indistinguishable(auth_client, records):
    foreign = auth_client.get(f"/api/v1/source-records/{records.foreign.id}/")
    missing = auth_client.get("/api/v1/source-records/00000000-0000-0000-0000-000000000000/")

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


@pytest.mark.django_db
def test_anonymous_list_is_forbidden(api_client):
    assert api_client.get("/api/v1/source-records/").status_code == 403


@pytest.mark.django_db
def test_list_of_fifty_rows_has_bounded_query_count(
    auth_client,
    fifty_normalized_records,
    django_assert_max_num_queries,
):
    with django_assert_max_num_queries(5):
        response = auth_client.get("/api/v1/source-records/?page_size=50")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 50
