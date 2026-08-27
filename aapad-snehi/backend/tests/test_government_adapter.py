import pytest

from app.adapters.base import AdapterConfigurationError
from app.adapters.government import validate_government_url


def test_government_feed_accepts_configured_authority_host():
    url = "https://alerts.mausam.imd.gov.in/feed.xml"
    assert validate_government_url(url, ("mausam.imd.gov.in",)) == url


def test_government_feed_accepts_current_imd_api_host():
    url = "https://api.imd.gov.in/api/v1/districtwarning"
    assert validate_government_url(url, ("api.imd.gov.in",)) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://mausam.imd.gov.in/feed.xml",
        "https://127.0.0.1/feed.xml",
        "https://169.254.169.254/latest/meta-data",
        "https://untrusted.example/feed.xml",
        "https://user:pass@mausam.imd.gov.in/feed.xml",
    ],
)
def test_government_feed_rejects_unsafe_or_unapproved_targets(url: str):
    with pytest.raises(AdapterConfigurationError):
        validate_government_url(url, ("mausam.imd.gov.in",))
