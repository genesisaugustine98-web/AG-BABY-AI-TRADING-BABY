from datetime import date

from scripts.backfill_h10_release_pages import declared_release_date, parse_release, release_at


def test_release_at_handles_dst_correctly() -> None:
    assert release_at(date(2021, 1, 4)).hour == 21
    assert release_at(date(2021, 7, 12)).hour == 20


def test_declared_release_date_is_read_from_page():
    html = '<div>Release Date: May 26, 2020</div>'
    assert declared_release_date(html) == date(2020, 5, 26)


def test_declared_release_date_rejects_missing_header():
    assert declared_release_date("<html></html>") is None


def test_parse_release_maps_dates_and_three_target_currencies() -> None:
    html = """
    <html><body><table>
      <tr><th>COUNTRY</th><th>CURRENCY</th><th>Dec. 28</th><th>Dec. 29</th><th>Dec. 30</th><th>Jan. 1</th></tr>
      <tr><td>*EMU MEMBERS</td><td>EURO</td><td>1.2213</td><td>1.2252</td><td>1.2280</td><td>ND</td></tr>
      <tr><td>*UNITED KINGDOM</td><td>POUND</td><td>1.3580</td><td>1.3600</td><td>1.3620</td><td>ND</td></tr>
      <tr><td>JAPAN</td><td>YEN</td><td>103.84</td><td>103.50</td><td>103.31</td><td>ND</td></tr>
    </table></body></html>
    """
    rows = parse_release(html, date(2021, 1, 4))
    assert len(rows) == 9
    assert {row["instrument"] for row in rows} == {
        "EURUSD_REFERENCE", "GBPUSD_REFERENCE", "USDJPY_REFERENCE"
    }
    assert all(row["execution_grade"] is False for row in rows)
    assert all(row["usable_at"].endswith("+00:00") for row in rows)
    assert all(row["event_time"].endswith("+00:00") for row in rows)
    assert rows[0]["source_version"] == "H10-release-2021-01-04"
