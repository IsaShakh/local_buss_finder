import pytest

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.campaigns.services import start_campaign
from apps.discovery.services import run_campaign_synchronously
from apps.sources.models import NormalizedSourceRecord, SourceRecord


@pytest.mark.django_db(transaction=True)
@pytest.mark.integration
def test_fixture_campaign_reaches_completed_with_raw_and_normalized_records(
    owner,
    alanya_campaign,
    s3_store,
    fixture_adapter_registry,
):
    start_campaign(
        campaign_id=alanya_campaign.id,
        actor=owner,
        enqueue=lambda _: None,
    )
    run_campaign_synchronously(
        alanya_campaign.id,
        get_adapter=fixture_adapter_registry.get,
        store=s3_store,
    )

    alanya_campaign.refresh_from_db()
    assert alanya_campaign.status == "completed"
    assert alanya_campaign.raw_records_found == 6
    assert alanya_campaign.normalized_records == 6
    assert SourceRecord.objects.filter(campaign=alanya_campaign).count() == 6
    assert (
        NormalizedSourceRecord.objects.filter(source_record__campaign=alanya_campaign).count() == 6
    )
    assert (
        BusinessSourceMembership.objects.filter(
            normalized_record__source_record__campaign=alanya_campaign
        ).count()
        == 6
    )
    assert Business.active.filter(owner=owner).count() == 5
    candidate = DuplicateCandidate.objects.get(owner=owner, status="pending")
    assert candidate.score == 75
    assert {signal["code"] for signal in candidate.signals} == {
        "exact_phone",
        "exact_name",
        "same_category",
    }
    assert candidate.left_business.display_name == "Fixture Meridian Dental"
    assert candidate.right_business.display_name == "Fixture Meridian Dental"
    shared = Business.active.get(owner=owner, display_name="Shared Alanya Dental")
    assert shared.memberships.count() == 2
    for record in SourceRecord.objects.filter(campaign=alanya_campaign):
        assert s3_store.get_json(record.raw_payload_key)
