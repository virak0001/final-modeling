# Cambodia Road Crash Portal

**Live portal:** https://cambodia-crash.xyz

A spatio-temporal data portal on road crashes in Cambodia, built from road-crash reports in Khmer-language news, the
2019 census and World Bank indicators for the 11 ASEAN members.

**Research question.** Where and when do the road crashes reported in Khmer-language news cluster, how much of the real
burden does that coverage capture, and how does Cambodia's road death rate compare with ASEAN?

**Hypotheses.**
- **H1a** Crashes reported outside Phnom Penh are more often fatal than those inside it.
- **H1b** Phnom Penh is over-reported relative to its population.
- **H2** Cambodia's road death rate rose from 2000 to 2019 while most ASEAN members' rates fell.

All three survived their tests (see the Findings page). The news sample also turned out to hold only about 5% of the deaths
the National Road Safety Committee counted in 2020-2024, which is the most important limit on everything else.

## Run it (three commands)

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m src.fetch && python -m src.pipeline      # pull World Bank + ODC, rebuild every processed table
streamlit run app.py                               # open http://localhost:8501
```

Tests: `python -m pytest -q`. Notebook: open `notebooks/analysis.ipynb` and choose **Restart and Run All**.

## What the portal does

| Requirement | Where |
|---|---|
| Live on the web | Streamlit Community Cloud, entry point `app.py` |
| Accepts uploads | **Upload data** page: checks columns, types and units; rejects duplicates within the file and rows already stored by an earlier upload; warns when a row matches a news-reported crash; lists rejected rows with every reason; stores accepted rows with the file name and date (`src/validate.py`) |
| Fetches data on its own | `.github/workflows/fetch.yml` every Monday, plus a **Refresh now** button (limited to once per 15 minutes); every pull is logged in `data/fetch_log.csv` (`src/fetch.py`) |
| Map | Provinces from the ODC census 2019 layer, shaded by reports or deaths per 100,000 person-years or by fatal share, with quantile class breaks in the legend; ASEAN countries by WHO-modelled road deaths per 100,000 |
| Time | Monthly series, STL trend and seasonal factors, change on a year earlier, a Holt-Winters forecast against a seasonal naive baseline on held-out 2024 |
| Linked views | Clicking a province filters the time chart and cards; the period slider re-colours the map; clicking an ASEAN country redraws its path |
| Data quality page | Every source with its licence, retrieval date, missing share and flagged outliers; missingness maps, join log, name-matching table, data dictionary |
| Findings page | Five findings, each one sentence with a number and the chart that proves it, computed live |
| Methods and ethics page | Every course week with the number behind its decision; feature selection with a pre-set rule (correlation heatmap, PCA variance kept, feature-group check and coefficients of the rare-event model) |

## Data sources and licences

| Source | Content | Licence | How it arrives |
|---|---|---|---|
| Khmer-language news (team dataset) | 1,074 articles reduced to 814 distinct crashes by `src/extract_accidents.py` | **Article text is copyright of each outlet** (85 rows carry a khmernews.news no-copying notice, 71 a VOD/CCIM footer). The raw workbook is kept out of this repository; only extracted fields are published in `data/processed/crashes_public.csv`. | Team collection, then the upload page |
| [ODC: Population census 2019, final totals](https://data.opendevelopmentcambodia.net/dataset/population-census-2019-final-population-totals) | Population, households, area and polygons for 25 provinces | CC BY-SA | ODC GeoServer WFS + CKAN API |
| [World Bank WDI](https://data.worldbank.org/) | `SH.STA.TRAF.P5` road mortality (WHO estimate), `SP.POP.TOTL`, `SP.URB.TOTL.IN.ZS`, `NY.GDP.PCAP.CD` for 11 ASEAN members | CC BY 4.0 | api.worldbank.org/v2 |
| Official national totals | Crashes, deaths and injured per year, 2020-2024: the National Road Safety Committee (NRSC) annual figures | Government statistics in public releases; no licence stated. The committee's report is not online, so each year is typed in from a ministry or state-media page, named per year in the file (see below) | `data/reference/official_totals.csv` |

Official totals, the page behind each year (all checked 2026-11-14):

| Year | Crashes | Deaths | Injured | Page |
|---|---|---|---|---|
| 2020 | 3,176 | 1,646 | 4,686 | [Phnom Penh Post, 2022-01-03](https://phnompenhpost.com/national/2021-fewer-road-accidents-deaths/) reporting the Interior Minister's year-end figures; agrees with the NRSC's stated changes for 2021 |
| 2021 | 2,670 | 1,497 | 3,615 | [Ministry of Public Works and Transport, 2022-02-09](https://www.mpwt.gov.kh/en/press/21695): the NRSC report at the year-end review |
| 2022 | 2,976 | 1,709 | 4,026 | [Ministry of Public Works and Transport, 2023-05-27](https://www.mpwt.gov.kh/en/press/31747), citing the NRSC report |
| 2023 | 3,317 | 1,590 | 4,515 | [Fresh News, 2024-01-30](https://m.freshnews.com.kh/localnews/326866-2024-01-30-03-46-32.html): the NRSC data sub-committee report, presented by the National Police |
| 2024 | 2,844 | 1,509 | 3,720 | [AKP state news agency, 2025-01-09](https://www.akp.gov.kh/post/detail/325620): the transport ministry's spokesperson |

WHO's modelled estimate for 2021 is about 3,000 deaths, roughly twice the national count, so the official series is itself a lower bound.

## Repository layout

```
app.py                          the portal (navigation)
pages/                          overview (map + time), findings, upload, data quality, methods and ethics
src/fetch.py                    one function per API, each pull logged
src/validate.py                 upload checks: columns, types, units
src/pipeline.py                 cleaning, joins, features, feature selection (correlation rule, feature-group check), time series,
                                tests of hypotheses, rare-event model
src/findings.py, src/charts.py  findings and figures shared by the portal and the notebook
src/names.py                    province name matching (English, Khmer, ISO and census spellings -> official code)
src/extract_accidents.py        rule-based extraction from Khmer news text (needs the local raw workbook)
data/raw/                       files as retrieved, never edited by hand (news workbook is local only)
data/processed/                 tables the portal reads
data/boundaries/                simplified province GeoJSON
data/reference/                 name-matching table, official totals, data dictionary
notebooks/analysis.ipynb        reproduces every number on the findings page
notebooks/severity_model.ipynb  earlier CRISP-DM severity model (failed its pre-set criterion on 2024; kept for the record)
tests/                          tests for validate.py, fetch.py and pipeline.py
.github/workflows/fetch.yml     the scheduled retrieval
```

## Deploy

The portal runs on its own AWS Lightsail server (1 GB RAM, Singapore) as two Docker containers defined in
`deploy/compose.yaml`: the app (`Dockerfile`) and Caddy (`deploy/Caddyfile`), which gets and renews the HTTPS certificate.
DNS for `cambodia-crash.xyz` is in Route 53. To ship a new version after pushing to `main`:

```bash
ssh ubuntu@<server> 'cd /opt/crash-portal && git pull && docker compose -f deploy/compose.yaml up -d --build'
```

Uploaded files live in the `uploads` Docker volume, so they survive restarts and new versions.

No API keys are needed. If one is ever added, pass it to the container as an environment variable, never in the code.
To make an upload part of the repository itself, copy its file out of the volume and commit it under `data/uploads/`.

## Limits

Reported crashes are the crashes that news chose to cover, so maps and time charts show coverage as much as risk. The monthly
"season" mostly follows when articles were collected. WHO road mortality is modelled, and per-person rates move the 2019 census
to other years with national growth.

## Team

_Add every member's name; make sure each member commits._
