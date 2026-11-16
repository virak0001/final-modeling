"""Retrieval tests use a fake HTTP session, so they run offline and never touch the real APIs."""
import pandas as pd
import pytest
import requests

from src import config, fetch


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, timeout))
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


WB_PAGE = [{"page": 1, "pages": 1, "per_page": 20000, "total": 2, "lastupdated": "2026-10-08"},
           [{"countryiso3code": "KHM", "country": {"value": "Cambodia"}, "date": "2019", "value": 19.6},
            {"countryiso3code": "THA", "country": {"value": "Thailand"}, "date": "2019", "value": None}]]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "RAW", tmp_path / "raw")


def test_parse_worldbank_keeps_nulls():
    data = fetch.parse_worldbank(WB_PAGE, "SH.STA.TRAF.P5")
    assert list(data.columns) == ["iso3", "country", "year", "indicator", "value"]
    assert len(data) == 2 and data.value.isna().sum() == 1 and data.year.dtype.kind == "i"


def test_parse_worldbank_error_message_raises():
    with pytest.raises(ValueError, match="no data"):
        fetch.parse_worldbank([{"message": [{"value": "Invalid indicator"}]}], "BAD")


def test_fetch_worldbank_logs_and_saves(tmp_path):
    log = tmp_path / "log.csv"
    session = FakeSession([FakeResponse(WB_PAGE)])
    data = fetch.fetch_worldbank("SH.STA.TRAF.P5", ["KHM", "THA"], 2019, 2019, session=session, log_path=log)
    assert len(data) == 2
    assert session.calls[0][2] == fetch.TIMEOUT and "KHM;THA" in session.calls[0][0]
    entry = pd.read_csv(log).iloc[-1]
    assert entry.status == "ok" and entry.rows == 1 and entry.source == "World Bank SH.STA.TRAF.P5"
    assert (config.RAW / "worldbank" / "SH.STA.TRAF.P5.json").exists()


def test_fetch_worldbank_follows_pages(tmp_path):
    page1 = [{**WB_PAGE[0], "pages": 2}, WB_PAGE[1]]
    page2 = [{**WB_PAGE[0], "page": 2, "pages": 2}, WB_PAGE[1]]
    session = FakeSession([FakeResponse(page1), FakeResponse(page2)])
    data = fetch.fetch_worldbank("X", ["KHM"], session=session, save=False, log_path=tmp_path / "log.csv")
    assert len(data) == 4 and len(session.calls) == 2


def test_failed_pull_is_logged_and_raised(tmp_path):
    log = tmp_path / "log.csv"
    session = FakeSession([FakeResponse({}, status=503)])
    with pytest.raises(requests.HTTPError):
        fetch.fetch_worldbank("SP.POP.TOTL", ["KHM"], session=session, log_path=log)
    assert len(session.calls) == 3  # retried
    entry = pd.read_csv(log).iloc[-1]
    assert entry.status == "failed" and entry.rows == 0


def census_feature(**props):
    base = {"pro_code": 12, "provinces": "Phnom Penh", "total": 2281951, "households": 499299, "area_km2": 679}
    base.update(props)
    return {"type": "Feature", "properties": base, "geometry": {"type": "Point", "coordinates": [104.9, 11.5]}}


def test_census_layer_checks_fields(tmp_path):
    log = tmp_path / "log.csv"
    good = FakeSession([FakeResponse({"type": "FeatureCollection", "features": [census_feature()]})])
    assert len(fetch.fetch_odc_census_layer(good, log_path=log)["features"]) == 1
    feature = census_feature()
    del feature["properties"]["total"]
    bad = FakeSession([FakeResponse({"type": "FeatureCollection", "features": [feature]})])
    with pytest.raises(ValueError, match="missing fields"):
        fetch.fetch_odc_census_layer(bad, log_path=log)
    assert list(pd.read_csv(log).status) == ["ok", "failed"]


def test_odc_package_reads_licence(tmp_path):
    body = {"success": True, "result": {"name": "x", "title": "X", "license_id": "cc-by-sa", "license_title": "CC BY-SA",
                                        "metadata_modified": "2024-01-01", "resources": [1, 2]}}
    meta = fetch.fetch_odc_package("x", FakeSession([FakeResponse(body)]), log_path=tmp_path / "log.csv")
    assert meta["license_id"] == "cc-by-sa" and meta["resources"] == 2


def test_fetch_all_continues_after_a_failure(monkeypatch):
    monkeypatch.setattr(fetch, "fetch_worldbank", lambda code, session=None: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(fetch, "fetch_odc_census_layer", lambda session=None: {"features": [1, 2, 3]})
    monkeypatch.setattr(fetch, "fetch_odc_package", lambda name, session=None: {"license_id": "cc"})
    results = fetch.fetch_all(session=object())
    assert [r["status"] for r in results].count("failed") == len(config.WORLDBANK_INDICATORS)
    assert {"source": "ODC census layer", "status": "ok", "rows": 3} in results
