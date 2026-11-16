"""Paths and reference tables shared by the portal, the notebook and the tests."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
BOUNDARIES = DATA / "boundaries"
REFERENCE = DATA / "reference"
UPLOADS = DATA / "uploads"

RAW_NEWS_XLSX = RAW / "news" / "Road_Accidents_Extracted.xlsx"  # local only: contains copyrighted article text
CRASHES_PUBLIC = PROCESSED / "crashes_public.csv"
PROVINCE_GEOJSON = BOUNDARIES / "khm_provinces_census2019.geojson"
CENSUS_CSV = PROCESSED / "census2019_province.csv"
WORLDBANK_CSV = PROCESSED / "worldbank_asean.csv"
OFFICIAL_TOTALS = REFERENCE / "official_totals.csv"
PROVINCE_NAMES = REFERENCE / "province_names.csv"
FETCH_LOG = DATA / "fetch_log.csv"
# On the server the log sits on the uploads volume (see deploy/compose.yaml), so it survives a new version.
UPLOAD_LOG = Path(os.environ.get("PORTAL_UPLOAD_LOG") or DATA / "upload_log.csv")
JOIN_LOG = PROCESSED / "join_log.csv"
RARE_EVENT_JSON = PROCESSED / "rare_event_results.json"
RARE_EVENT_CASES = PROCESSED / "rare_event_test_cases.csv"
RARE_EVENT_COSTS = PROCESSED / "rare_event_cost_curve.csv"
DATA_DICTIONARY = REFERENCE / "data_dictionary.csv"

RANDOM_STATE = 42

# Analysis window: before 2018 the news sample has fewer than 12 reports a year.
SERIES_START, SERIES_END = "2018-01", "2024-12"
TEST_YEAR = 2024

# ASEAN has 11 members since Timor-Leste joined in October 2025.
ASEAN = {
    "BRN": "Brunei", "KHM": "Cambodia", "IDN": "Indonesia", "LAO": "Lao PDR", "MYS": "Malaysia", "MMR": "Myanmar",
    "PHL": "Philippines", "SGP": "Singapore", "THA": "Thailand", "TLS": "Timor-Leste", "VNM": "Viet Nam",
}

WORLDBANK_INDICATORS = {
    "SH.STA.TRAF.P5": "road_deaths_per_100k",  # WHO modelled estimate
    "SP.POP.TOTL": "population",
    "SP.URB.TOTL.IN.ZS": "urban_share_pct",
    "NY.GDP.PCAP.CD": "gdp_per_capita_usd",
}

ODC_CKAN = "https://data.opendevelopmentcambodia.net/en/api/3/action"
ODC_WFS = "https://data.opendevelopmentcambodia.net/geoserver/ODCambodia/ows"
ODC_CENSUS_PACKAGE = "population-census-2019-final-population-totals"
ODC_CENSUS_LAYER = "ODCambodia:final_census2019_en"
WORLDBANK_API = "https://api.worldbank.org/v2"

SEVERITIES = ["Fatal", "Injury", "Property damage only", "Not stated"]
TIME_OF_DAY = ["Morning (05-11)", "Afternoon (12-16)", "Evening (17-20)", "Night (21-04)"]
ROAD_TYPES = ["National road", "Expressway", "City street", "Local road", "Unclassified", "Unknown"]

# Name-matching table. Key is the official province code used by NIS and the census layer.
# portal = spelling used by the news extractor and this portal; census = spelling in the ODC census layer.
PROVINCES = [
    # code, iso_3166_2, portal, census, khmer, extra aliases
    (1, "KH-1", "Banteay Meanchey", "Banteay Meanchey", "បន្ទាយមានជ័យ", "Banteay Mean Chey"),
    (2, "KH-2", "Battambang", "Battambang", "បាត់ដំបង", "Batdambang"),
    (3, "KH-3", "Kampong Cham", "Kampong Cham", "កំពង់ចាម", "Kompong Cham"),
    (4, "KH-4", "Kampong Chhnang", "Kampong Chhnang", "កំពង់ឆ្នាំង", "Kompong Chhnang"),
    (5, "KH-5", "Kampong Speu", "Kampong Speu", "កំពង់ស្ពឺ", "Kompong Speu|Kampong Spoe"),
    (6, "KH-6", "Kampong Thom", "Kampong Thom", "កំពង់ធំ", "Kompong Thom"),
    (7, "KH-7", "Kampot", "Kampot", "កំពត", "Kampaot"),
    (8, "KH-8", "Kandal", "Kandal", "កណ្តាល", "កណ្ដាល"),
    (9, "KH-9", "Koh Kong", "Koh Kong", "កោះកុង", "Kaoh Kong"),
    (10, "KH-10", "Kratie", "Kratie", "ក្រចេះ", "Kracheh|Kratié"),
    (11, "KH-11", "Mondulkiri", "Mondul Kiri", "មណ្ឌលគិរី", "មណ្ឌលគីរី|Mondol Kiri"),
    (12, "KH-12", "Phnom Penh", "Phnom Penh", "ភ្នំពេញ", "Phnum Penh"),
    (13, "KH-13", "Preah Vihear", "Preah Vihear", "ព្រះវិហារ", "Preah Vihéar"),
    (14, "KH-14", "Prey Veng", "Prey Veng", "ព្រៃវែង", "Prey Veaeng"),
    (15, "KH-15", "Pursat", "Pursat", "ពោធិ៍សាត់", "ពោធិសាត់|Pouthisat"),
    (16, "KH-16", "Ratanakiri", "Ratanak Kiri", "រតនគិរី", "រតនគីរី|Rotanak Kiri|Ratanakkiri"),
    (17, "KH-17", "Siem Reap", "Siem Reap", "សៀមរាប", "Siemreap|Siem Riep"),
    (18, "KH-18", "Preah Sihanouk", "Preah Sihanouk", "ព្រះសីហនុ", "Sihanoukville|Kampong Som|Krong Preah Sihanouk"),
    (19, "KH-19", "Stung Treng", "Stung Treng", "ស្ទឹងត្រែង", "Stueng Traeng"),
    (20, "KH-20", "Svay Rieng", "Svay Rieng", "ស្វាយរៀង", "Svay Rieng"),
    (21, "KH-21", "Takeo", "Takeo", "តាកែវ", "Takéo"),
    (22, "KH-22", "Oddar Meanchey", "Otdar Meanchey", "ឧត្តរមានជ័យ", "ឧត្ដរមានជ័យ|Oddor Meanchey|Otdar Mean Chey"),
    (23, "KH-23", "Kep", "Kep", "កែប", "Kaeb"),
    (24, "KH-24", "Pailin", "Pailin", "ប៉ៃលិន", "Krong Pailin"),
    (25, "KH-25", "Tbong Khmum", "Tbong Khmum", "ត្បូងឃ្មុំ", "Tboung Khmum|Tbong Khmom"),
]
