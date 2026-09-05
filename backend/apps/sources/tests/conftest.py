import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def fake_s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="raw-test")
        yield client
