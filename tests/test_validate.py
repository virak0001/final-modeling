import pandas as pd
import pytest

from src import validate
from src.names import match_province


def frame(**overrides):
    row = {"incident_date": "2024-03-14", "province": "Kampong Cham", "deaths": "1", "injuries_total": "2"}
    row.update(overrides)
    return pd.DataFrame([row])


def reasons(result):
    return " | ".join(result.rejected.reasons)


def test_good_row_is_accepted_and_severity_derived():
    result = validate.validate_crash_upload(frame())
    assert result.ok and len(result.accepted) == 1 and result.rejected.empty
    assert result.accepted.loc[0, "severity"] == "Fatal"
    assert result.accepted.loc[0, "province"] == "Kampong Cham"


def test_header_aliases_are_recognised():
    data = pd.DataFrame([{"Date": "2024-01-02", "Province": "Takeo", "Killed": "0", "Injured": "3"}])
    result = validate.validate_crash_upload(data)
    assert result.ok and result.accepted.loc[0, "severity"] == "Injury"


def test_missing_required_column_rejects_whole_file():
    result = validate.validate_crash_upload(frame().drop(columns=["deaths"]))
    assert not result.ok and "deaths" in result.file_errors[0]


def test_rate_column_is_rejected_as_wrong_unit():
    data = frame().rename(columns={"deaths": "deaths_per_100k"})
    result = validate.validate_crash_upload(data)
    assert any("rates or percentages" in e for e in result.file_errors)


@pytest.mark.parametrize("overrides, expected", [
    ({"incident_date": "not a date"}, "is not a date"),
    ({"incident_date": "2999-01-01"}, "outside 2000-01-01 to today"),
    ({"incident_date": "1995-05-01"}, "outside 2000-01-01 to today"),
    ({"province": "Bangkok"}, "not a Cambodian province"),
    ({"deaths": "-1"}, "deaths is negative"),
    ({"deaths": "1.5"}, "not a whole number"),
    ({"deaths": "abc"}, "is not a number"),
    ({"deaths": ""}, "is empty"),
    ({"deaths": "250"}, "period total"),
    ({"deaths": "nan"}, "is not a number"),
    ({"deaths": "inf"}, "is not a number"),
    ({"incident_date": "2024"}, "no full day, month and year"),
    ({"incident_date": "March 2024"}, "no full day, month and year"),
    ({"incident_date": "today"}, "is not a date"),
    ({"severity": "Fatal", "deaths": "0"}, "contradicts"),
    ({"severity": "Terrible"}, "is not one of"),
    ({"time_of_day": "midnight"}, "time_of_day 'midnight'"),
    ({"veh_motorcycle": "yes"}, "must be 0 or 1"),
])
def test_bad_rows_are_rejected_with_reason(overrides, expected):
    result = validate.validate_crash_upload(frame(**overrides))
    assert result.accepted.empty
    assert expected in reasons(result)


def test_all_reasons_are_listed_for_one_row():
    result = validate.validate_crash_upload(frame(province="Paris", deaths="-2"))
    assert "province" in reasons(result) and "negative" in reasons(result)


def test_slash_dates_are_read_day_first_and_flagged_when_ambiguous():
    for text, expected in (("14/03/2024", "2024-03-14"), ("03/14/2024", "2024-03-14"), ("03/04/2024", "2024-04-03"),
                           ("14.03.2024", "2024-03-14"), ("2024-03-14T10:00:00+07:00", "2024-03-14")):
        result = validate.validate_crash_upload(frame(incident_date=text))
        assert str(result.accepted.incident_date.iloc[0].date()) == expected, text
    assert any("day/month/year" in w for w in validate.validate_crash_upload(frame(incident_date="03/04/2024")).warnings)
    assert not validate.validate_crash_upload(frame(incident_date="14/03/2024")).warnings


def test_rows_already_stored_by_an_earlier_upload_are_rejected():
    existing = pd.DataFrame([{"incident_date": pd.Timestamp("2024-03-14"), "province": "Kampong Cham", "deaths": 1,
                              "injuries_total": 2, "road_name": None, "source_file": "first.csv", "uploaded_at_utc": "20260101T000000Z"}])
    result = validate.validate_crash_upload(pd.concat([frame(), frame(deaths="3")], ignore_index=True), existing=existing)
    assert len(result.accepted) == 1 and result.accepted.deaths.iloc[0] == 3
    assert "already stored from an earlier upload: first.csv" in reasons(result)


def test_possible_matches_flags_rows_that_look_like_news_crashes():
    accepted = validate.validate_crash_upload(pd.concat([frame(), frame(province="Takeo")], ignore_index=True)).accepted
    news = pd.DataFrame({"incident_date": pd.to_datetime(["2024-03-14"]), "province": ["Kampong Cham"], "deaths": [1.0],
                         "injuries_total": [2.0]})
    assert validate.possible_matches(accepted, news).tolist() == [True, False]
    assert not validate.possible_matches(accepted, pd.DataFrame()).any()


def test_read_upload_handles_utf16_and_cp1252_csv():
    text = frame(province="Takéo").to_csv(index=False)
    assert validate.read_upload("a.csv", text.encode("utf-16")).loc[0, "province"] == "Takéo"
    assert validate.read_upload("a.csv", text.encode("cp1252")).loc[0, "province"] == "Takéo"


def test_duplicates_within_file_are_rejected():
    data = pd.concat([frame(), frame()], ignore_index=True)
    result = validate.validate_crash_upload(data)
    assert len(result.accepted) == 1 and "duplicate of line 2" in reasons(result)


@pytest.mark.parametrize("name, expected", [
    ("តាកែវ", "Takeo"), ("KH-12", "Phnom Penh"), ("12", "Phnom Penh"), ("Otdar Meanchey", "Oddar Meanchey"),
    ("Mondul Kiri", "Mondulkiri"), ("Ratanak Kiri", "Ratanakiri"), ("Sihanoukville", "Preah Sihanouk"),
    ("ខេត្តកណ្ដាល", "Kandal"), ("Siem Reap Province", "Siem Reap"), ("Hanoi", None), ("", None),
])
def test_province_matching(name, expected):
    assert match_province(name) == expected


def test_read_upload_rejects_other_types_and_large_files():
    with pytest.raises(ValueError, match="not accepted"):
        validate.read_upload("crashes.txt", b"a,b")
    with pytest.raises(ValueError, match="limit"):
        validate.read_upload("crashes.csv", b"x" * (validate.MAX_BYTES + 1))


def test_read_upload_reads_csv_and_excel(tmp_path):
    csv_bytes = frame().to_csv(index=False).encode("utf-8")
    assert validate.read_upload("a.csv", csv_bytes).shape == (1, 4)
    path = tmp_path / "a.xlsx"
    frame().to_excel(path, index=False)
    assert validate.read_upload("a.xlsx", path.read_bytes()).loc[0, "province"] == "Kampong Cham"


def test_store_upload_saves_rows_with_name_and_date(tmp_path):
    data = pd.concat([frame(), frame(province="Nowhere"), frame(road_name="=HYPERLINK(1)")], ignore_index=True)
    result = validate.validate_crash_upload(data)
    entry = validate.store_upload(result, "../../evil name.csv", tmp_path / "uploads", tmp_path / "log.csv")
    stored = tmp_path / "uploads" / entry["stored_as"]
    assert stored.exists() and stored.parent == tmp_path / "uploads"
    saved = pd.read_csv(stored)
    assert set(saved.source_file) == {"evil_name.csv"} and "uploaded_at_utc" in saved
    assert saved.road_name.dropna().str.startswith("'=").all()  # formula defused
    log = pd.read_csv(tmp_path / "log.csv")
    assert log.loc[0, "rows_accepted"] == 2 and log.loc[0, "rows_rejected"] == 1
    assert len(validate.load_uploads(tmp_path / "uploads")) == 2
