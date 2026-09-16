from datetime import date

from scripts.ingest_h10_historical import build_historical_url


def test_historical_url_contains_explicit_date_range():
    url = build_historical_url(date(2020, 1, 1), date(2020, 12, 31))
    assert "from=01%2F01%2F2020" in url
    assert "to=12%2F31%2F2020" in url
    assert "rel=H10" in url
    assert "series=60f32914ab61dfab590e0e470153e3ae" in url
