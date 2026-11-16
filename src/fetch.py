"""Automatic retrieval. One function per API; every pull is appended to data/fetch_log.csv.

Run all pulls:  python -m src.fetch
Raw responses are saved unchanged under data/raw/ so the processing step can be re-run offline.
"""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src import config

HEADERS = {"User-Agent": "cambodia-road-crash-portal/1.0 (student research project)"}
TIMEOUT = 60
LOG_FIELDS = ["retrieved_at_utc", "source", "url", "rows", "status", "message"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_pull(source: str, url: str, rows: int, status: str, message: str = "", log_path: Path | None = None) -> dict:
    """Append one line to the fetch log and return it."""
    log_path = Path(log_path or config.FETCH_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"retrieved_at_utc": _now(), "source": source, "url": url, "rows": int(rows), "status": status,
             "message": str(message)[:300]}
    new_file = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(entry)
    return entry


def read_fetch_log(log_path: Path | None = None) -> pd.DataFrame:
    log_path = Path(log_path or config.FETCH_LOG)
    if not log_path.exists():
        return pd.DataFrame(columns=LOG_FIELDS)
    return pd.read_csv(log_path)


def _get(session, url: str, params: dict | None = None, retries: int = 3):
    """GET with a timeout and simple back-off. Raises after the last failure."""
    last_error = None
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as error:  # network errors and HTTP 4xx/5xx
            last_error = error
            time.sleep(2 ** attempt)
    raise last_error


def parse_worldbank(payload: list, indicator: str) -> pd.DataFrame:
    """Turn one page of the World Bank v2 JSON into tidy rows: iso3, year, indicator, value."""
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        message = payload[0].get("message") if isinstance(payload, list) and payload and isinstance(payload[0], dict) else payload
        raise ValueError(f"World Bank returned no data for {indicator}: {message}")
    rows = [{"iso3": r["countryiso3code"], "country": r["country"]["value"], "year": int(r["date"]),
             "indicator": indicator, "value": r["value"]} for r in payload[1]]
    return pd.DataFrame(rows)


def fetch_worldbank(indicator: str, countries=None, start: int = 1990, end: int | None = None,
                    session=None, save: bool = True, log_path: Path | None = None) -> pd.DataFrame:
    """World Bank Indicators API (no key). Returns one row per country-year, nulls included."""
    session = session or requests.Session()
    countries = countries or list(config.ASEAN)
    end = end or datetime.now().year
    url = f"{config.WORLDBANK_API}/country/{';'.join(countries)}/indicator/{indicator}"
    source = f"World Bank {indicator}"
    try:
        frames, page, pages, raw_pages = [], 1, 1, []
        while page <= pages:
            payload = _get(session, url, {"format": "json", "per_page": 20000, "date": f"{start}:{end}", "page": page}).json()
            raw_pages.append(payload)
            frames.append(parse_worldbank(payload, indicator))
            pages = int(payload[0].get("pages", 1))
            page += 1
        data = pd.concat(frames, ignore_index=True)
        if save:
            out = config.RAW / "worldbank" / f"{indicator}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(raw_pages), encoding="utf-8")
        log_pull(source, url, data.value.notna().sum(), "ok", f"{len(data)} country-years, last updated "
                 f"{raw_pages[0][0].get('lastupdated', '?')}", log_path)
        return data
    except Exception as error:
        log_pull(source, url, 0, "failed", repr(error), log_path)
        raise


def fetch_odc_package(name: str, session=None, save: bool = True, log_path: Path | None = None) -> dict:
    """ODC CKAN package metadata: licence, last modified, resources. Used on the data-quality page."""
    session = session or requests.Session()
    url = f"{config.ODC_CKAN}/package_show"
    source = f"ODC CKAN package {name}"
    try:
        body = _get(session, url, {"id": name}).json()
        if not body.get("success"):
            raise ValueError(body.get("error"))
        package = body["result"]
        meta = {"name": package["name"], "title": package.get("title"), "license_id": package.get("license_id"),
                "license_title": package.get("license_title"), "metadata_modified": package.get("metadata_modified"),
                "url": f"https://data.opendevelopmentcambodia.net/dataset/{package['name']}",
                "retrieved_at_utc": _now(), "resources": len(package.get("resources", []))}
        if save:
            out = config.RAW / "odc" / f"{name}.meta.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        log_pull(source, url, 1, "ok", f"licence {meta['license_id']}", log_path)
        return meta
    except Exception as error:
        log_pull(source, url, 0, "failed", repr(error), log_path)
        raise


def fetch_odc_census_layer(session=None, save: bool = True, log_path: Path | None = None) -> dict:
    """Census 2019 final totals by province, with province polygons, from the ODC GeoServer (WFS, GeoJSON, WGS84)."""
    session = session or requests.Session()
    params = {"service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": config.ODC_CENSUS_LAYER,
              "outputFormat": "application/json", "srsName": "EPSG:4326"}
    source = "ODC GeoServer census 2019 provinces"
    try:
        geojson = _get(session, config.ODC_WFS, params).json()
        features = geojson.get("features") or []
        if not features:
            raise ValueError("WFS returned no features")
        missing = {"pro_code", "provinces", "total", "households", "area_km2"} - set(features[0]["properties"])
        if missing:
            raise ValueError(f"census layer is missing fields {sorted(missing)}")
        if save:
            out = config.RAW / "odc" / "final_census2019_en.geojson"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
        log_pull(source, config.ODC_WFS, len(features), "ok", "", log_path)
        return geojson
    except Exception as error:
        log_pull(source, config.ODC_WFS, 0, "failed", repr(error), log_path)
        raise


def fetch_all(session=None) -> list[dict]:
    """Run every automatic source. One failure does not stop the others."""
    session = session or requests.Session()
    jobs = [(f"World Bank {code}", lambda code=code: fetch_worldbank(code, session=session))
            for code in config.WORLDBANK_INDICATORS]
    jobs += [("ODC census layer", lambda: fetch_odc_census_layer(session=session)),
             ("ODC census metadata", lambda: fetch_odc_package(config.ODC_CENSUS_PACKAGE, session=session))]
    results = []
    for name, job in jobs:
        try:
            out = job()
            rows = len(out["features"]) if isinstance(out, dict) and "features" in out else (len(out) if isinstance(out, pd.DataFrame) else 1)
            results.append({"source": name, "status": "ok", "rows": rows})
        except Exception as error:
            results.append({"source": name, "status": "failed", "rows": 0, "message": repr(error)})
    return results


if __name__ == "__main__":
    for result in fetch_all():
        print(result)
