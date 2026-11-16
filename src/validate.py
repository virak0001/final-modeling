"""Upload checks for new crash records: columns, types and units.

A file is rejected outright when it cannot be read or misses a required column.
Otherwise each row is checked; bad rows are returned with every reason, good rows are stored
with the original file name and the upload time.
"""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dateutil import parser as dateparser

from src import config
from src.names import match_province

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
MAX_DEATHS, MAX_INJURIES = 100, 300  # per crash; larger numbers are almost always period totals
EARLIEST = pd.Timestamp("2000-01-01")

REQUIRED = ["incident_date", "province", "deaths", "injuries_total"]
FLAG_COLUMNS = [f"veh_{v}" for v in ("motorcycle", "car_or_light_vehicle", "heavy_truck", "bus_or_van", "tuk_tuk",
                                     "bicycle", "pedestrian", "tractor")] + \
               [f"factor_{f}" for f in ("speeding", "drunk_driving", "careless_driving", "wrong_way", "overtaking",
                                        "lost_control", "brake_failure", "tyre_burst", "fatigue", "wet_road_or_rain",
                                        "turning_or_crossing", "phone_use")]
OPTIONAL = ["severity", "time_of_day", "road_type", "road_name", "source", *FLAG_COLUMNS]
ALIASES = {
    "date": "incident_date", "crash_date": "incident_date", "accident_date": "incident_date",
    "location": "province", "province_name": "province", "khaet": "province",
    "killed": "deaths", "dead": "deaths", "fatalities": "deaths", "number_of_deaths": "deaths",
    "injuries": "injuries_total", "injured": "injuries_total", "number_injured": "injuries_total",
    "outlet": "source", "source_url": "source",
}
UNIT_HINT = re.compile(r"(%|percent|per_?cent|per_?100k|rate|ratio|share)")
SLASH_DATE = re.compile(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})$")  # read as day/month/year
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


@dataclass
class UploadResult:
    ok: bool
    accepted: pd.DataFrame = field(default_factory=pd.DataFrame)
    rejected: pd.DataFrame = field(default_factory=pd.DataFrame)
    file_errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    rows_received: int = 0


def normalise_header(name: str) -> str:
    key = re.sub(r"[^0-9a-z%]+", "_", str(name).strip().lower()).strip("_")
    return ALIASES.get(key, key)


def read_upload(name: str, content: bytes) -> pd.DataFrame:
    """Read CSV or Excel as text so that types are checked here, not guessed by pandas."""
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {suffix or '(none)'} is not accepted. Use .csv or .xlsx.")
    if len(content) > MAX_BYTES:
        raise ValueError(f"File is {len(content) / 1e6:.1f} MB; the limit is {MAX_BYTES // 1024 // 1024} MB.")
    if suffix == ".csv":
        # UTF-16 is tried only behind its byte-order mark: almost any bytes "decode" as UTF-16, into nonsense.
        encodings = ("utf-16",) if content[:2] in UTF16_BOMS else ("utf-8-sig", "cp1252")
        for encoding in encodings:
            try:
                return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not read the CSV text encoding. Save it as UTF-8.")
    return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False, engine="openpyxl")


def _as_count(value: str):
    """Parse a whole number of people. Returns (number, problem)."""
    text = str(value).strip().replace(",", "")
    if text == "":
        return None, "is empty (enter 0 if there were none)"
    try:
        number = float(text)
    except ValueError:
        return None, f"'{value}' is not a number"
    if not math.isfinite(number):  # 'nan' and 'inf' are floats, but int() of them raises
        return None, f"'{value}' is not a number"
    if number < 0:
        return None, "is negative"
    if number != int(number):
        return None, f"{value} is not a whole number of people"
    return int(number), None


def _as_date(value: str):
    """Parse a full calendar date. A year alone, a month and year, or a word such as 'today' is refused:
    a lenient parser would silently turn them into the first of the month or into the upload date."""
    text = str(value).strip()
    if not text:
        return None, "is empty"
    try:
        slash = SLASH_DATE.match(text)
        if slash:
            day, month, year = (int(g) for g in slash.groups())
            if month > 12 >= day:  # only month/day/year can be meant
                day, month = month, day
            parsed = pd.Timestamp(year=year, month=month, day=day)
        else:
            # Parse twice with different defaults: a part that was not in the text takes the default and differs.
            first = dateparser.parse(text, default=datetime(2000, 1, 1))
            second = dateparser.parse(text, default=datetime(2001, 2, 2))
            if (first.year, first.month, first.day) != (second.year, second.month, second.day):
                return None, f"'{value}' gives no full day, month and year (use YYYY-MM-DD)"
            parsed = pd.Timestamp(first)
    except (ValueError, OverflowError):  # dateutil's ParserError is a ValueError
        return None, f"'{value}' is not a date (use YYYY-MM-DD)"
    parsed = parsed.tz_localize(None) if parsed.tzinfo else parsed
    if parsed < EARLIEST or parsed > pd.Timestamp.now().normalize() + pd.Timedelta(days=1):
        return None, f"{parsed.date()} is outside 2000-01-01 to today"
    return parsed.normalize(), None


def implied_severity(deaths: int, injuries: int) -> str:
    return "Fatal" if deaths > 0 else ("Injury" if injuries > 0 else "Property damage only")


def _row_key(date, province, deaths, injuries, road_name) -> tuple:
    """What makes two rows the same crash: date, province, casualties and the road named."""
    road = "" if road_name is None or (isinstance(road_name, float) and pd.isna(road_name)) else str(road_name)
    return (pd.Timestamp(date).normalize(), province, int(deaths), int(injuries), road.lstrip("'"))


def stored_keys(existing: pd.DataFrame | None) -> dict:
    """Row key -> 'file (upload time)' for every row already stored by an earlier upload."""
    keys = {}
    if existing is None or existing.empty:
        return keys
    for row in existing.itertuples(index=False):
        if pd.isna(row.incident_date) or pd.isna(row.deaths) or pd.isna(row.injuries_total):
            continue
        key = _row_key(row.incident_date, row.province, row.deaths, row.injuries_total, getattr(row, "road_name", ""))
        keys.setdefault(key, f"{getattr(row, 'source_file', 'an earlier file')} ({getattr(row, 'uploaded_at_utc', '')})")
    return keys


def validate_crash_upload(frame: pd.DataFrame, existing: pd.DataFrame | None = None) -> UploadResult:
    """Check every row. Rows with any problem are rejected with all their reasons listed.
    `existing` is the table of rows stored by earlier uploads; a row already there is rejected as a duplicate."""
    result = UploadResult(ok=False, rows_received=len(frame))
    frame = frame.rename(columns=normalise_header)
    if frame.columns.duplicated().any():
        result.file_errors.append(f"Duplicate columns after renaming: {sorted(set(frame.columns[frame.columns.duplicated()]))}")
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        result.file_errors.append(f"Missing required column(s): {', '.join(missing)}. Required: {', '.join(REQUIRED)}.")
    rate_columns = [c for c in frame.columns if UNIT_HINT.search(str(c)) and re.search(r"death|injur|kill|fatal", str(c))]
    if rate_columns:
        result.file_errors.append(f"Column(s) {rate_columns} look like rates or percentages. "
                                  "Upload counts of people per crash, one row per crash.")
    if len(frame) == 0:
        result.file_errors.append("The file has no data rows.")
    if len(frame) > MAX_ROWS:
        result.file_errors.append(f"The file has {len(frame):,} rows; the limit is {MAX_ROWS:,}.")
    if result.file_errors:
        return result

    ignored = [c for c in frame.columns if c not in REQUIRED + OPTIONAL]
    if ignored:
        result.warnings.append(f"Ignored unknown column(s): {', '.join(map(str, ignored[:12]))}")
    ambiguous = [t for t in frame.incident_date.astype(str).str.strip() if (m := SLASH_DATE.match(t))
                 and int(m.group(1)) <= 12 and int(m.group(2)) <= 12 and m.group(1) != m.group(2)]
    if ambiguous:
        result.warnings.append(f"{len(ambiguous)} date(s) such as {ambiguous[0]} were read as day/month/year. "
                               "Write dates as YYYY-MM-DD to avoid doubt.")

    already = stored_keys(existing)
    accepted, rejected, seen = [], [], {}
    for position, row in enumerate(frame.to_dict("records")):
        line = position + 2  # header is line 1 in a spreadsheet
        reasons, clean = [], {}

        date, problem = _as_date(row["incident_date"])
        if problem:
            reasons.append(f"incident_date {problem}")
        clean["incident_date"] = date

        province = match_province(row["province"])
        if province is None:
            reasons.append(f"province '{row['province']}' is not a Cambodian province name or code")
        clean["province"] = province

        for column, limit in (("deaths", MAX_DEATHS), ("injuries_total", MAX_INJURIES)):
            number, problem = _as_count(row[column])
            if problem:
                reasons.append(f"{column} {problem}")
            elif number > limit:
                reasons.append(f"{column} = {number} is above {limit} for one crash; is this a period total?")
            clean[column] = number

        if clean["deaths"] is not None and clean["injuries_total"] is not None:
            implied = implied_severity(clean["deaths"], clean["injuries_total"])
            given = str(row.get("severity", "")).strip()
            if given and given not in config.SEVERITIES:
                reasons.append(f"severity '{given}' is not one of {config.SEVERITIES}")
            elif given and given != "Not stated" and given != implied:
                reasons.append(f"severity '{given}' contradicts deaths={clean['deaths']}, injuries={clean['injuries_total']}")
            clean["severity"] = implied

        for column, allowed in (("time_of_day", config.TIME_OF_DAY), ("road_type", config.ROAD_TYPES)):
            value = str(row.get(column, "")).strip()
            if value and value not in allowed and value != "Unknown":
                reasons.append(f"{column} '{value}' is not one of {allowed}")
            clean[column] = value or "Unknown"

        for column in FLAG_COLUMNS:
            value = str(row.get(column, "")).strip()
            if value not in ("", "0", "1", "0.0", "1.0"):
                reasons.append(f"{column} must be 0 or 1, got '{value}'")
            clean[column] = int(float(value)) if value in ("0", "1", "0.0", "1.0") else 0

        clean["road_name"] = str(row.get("road_name", "")).strip()[:40]
        clean["source"] = str(row.get("source", "")).strip()[:200]

        if not reasons:
            key = _row_key(clean["incident_date"], clean["province"], clean["deaths"], clean["injuries_total"], clean["road_name"])
            if key in seen:
                reasons.append(f"duplicate of line {seen[key]} (same date, province, road and casualties)")
            elif key in already:
                reasons.append(f"already stored from an earlier upload: {already[key]}")
            else:
                seen[key] = line

        if reasons:
            rejected.append({"line": line, "reasons": "; ".join(reasons),
                             **{k: row.get(k, "") for k in REQUIRED}})
        else:
            accepted.append(clean)

    result.accepted = pd.DataFrame(accepted)
    result.rejected = pd.DataFrame(rejected, columns=["line", "reasons", *REQUIRED])
    result.ok = len(result.accepted) > 0
    return result


def safe_filename(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(str(name)).name).strip("._") or "upload"
    return stem[:80]


def _defuse(value):
    """Stop spreadsheet formula injection when stored text is opened in Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def store_upload(result: UploadResult, file_name: str, upload_dir: Path | None = None,
                 log_path: Path | None = None) -> dict:
    """Save accepted (and rejected) rows with the file name and upload time, and log the upload."""
    upload_dir = Path(upload_dir or config.UPLOADS)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{stamp}_{Path(safe_filename(file_name)).stem}"
    stored_as = ""
    if len(result.accepted):
        accepted = result.accepted.assign(source_file=safe_filename(file_name), uploaded_at_utc=stamp)
        stored_as = f"{base}.csv"
        accepted.map(_defuse).to_csv(upload_dir / stored_as, index=False, encoding="utf-8")
    if len(result.rejected):
        result.rejected.map(_defuse).to_csv(upload_dir / f"{base}.rejected.csv", index=False, encoding="utf-8")

    entry = {"uploaded_at_utc": stamp, "file_name": safe_filename(file_name), "stored_as": stored_as,
             "rows_received": result.rows_received, "rows_accepted": len(result.accepted),
             "rows_rejected": len(result.rejected)}
    log_path = Path(log_path or config.UPLOAD_LOG)
    new_file = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(entry))
        if new_file:
            writer.writeheader()
        writer.writerow(entry)
    return entry


def possible_matches(accepted: pd.DataFrame, reference: pd.DataFrame | None) -> pd.Series:
    """Accepted rows that match a crash already in the portal on date, province and casualties.
    A warning, not a rejection: two sources can report one crash, and only a person can tell."""
    if accepted.empty or reference is None or reference.empty:
        return pd.Series(False, index=accepted.index)
    columns = ["incident_date", "province", "deaths", "injuries_total"]
    known = reference.dropna(subset=columns)
    keys = set(zip(pd.to_datetime(known.incident_date).dt.normalize(), known.province, known.deaths.astype(int),
                   known.injuries_total.astype(int)))
    return pd.Series([(pd.Timestamp(d).normalize(), p, int(k), int(i)) in keys for d, p, k, i in
                      zip(accepted.incident_date, accepted.province, accepted.deaths, accepted.injuries_total)],
                     index=accepted.index)


def load_uploads(upload_dir: Path | None = None) -> pd.DataFrame:
    """All stored upload rows, ready to append to the curated crash table."""
    upload_dir = Path(upload_dir or config.UPLOADS)
    files = sorted(p for p in upload_dir.glob("*.csv") if not p.name.endswith(".rejected.csv"))
    if not files:
        return pd.DataFrame()
    frames = [pd.read_csv(p, parse_dates=["incident_date"]) for p in files]
    return pd.concat(frames, ignore_index=True)
