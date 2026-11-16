"""Rule-based extraction of structured crash fields from Khmer news text.

Reads the two-column workbook (Filename, Crash_Description) and writes a new
workbook with one row per article. Every field is a best-effort extraction, so
ambiguous values stay blank and carry a flag instead of a guess.

Usage: python extract_accidents.py input.xlsx output.xlsx
"""
import re
import sys
from collections import Counter
from datetime import date

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

K2A = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")
ZW = re.compile("[​‌‍﻿­]")
KH = "ក-៿"

MONTH_VARIANTS = {
    1: ["មករា"], 2: ["កុម្ភៈ", "កុម្ភះ", "កុម្ភ"], 3: ["មីនា", "មិនា"], 4: ["មេសា"], 5: ["ឧសភា"],
    6: ["មិថុនា"], 7: ["កក្កដា", "កក្ដដា"], 8: ["សីហា"], 9: ["កញ្ញា"], 10: ["តុលា"],
    11: ["វិច្ឆិកា", "វិច្ឆិការ", "វិច្ឆកា"], 12: ["ធ្នូរ", "ធ្នូ"],
}
EN_MONTHS = "January February March April May June July August September October November December".split()
MONTHS = {v: m for m, vs in MONTH_VARIANTS.items() for v in vs}
MONTHS.update({m: i + 1 for i, m in enumerate(EN_MONTHS)})
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

PROVINCES = {
    "Phnom Penh": ["ភ្នំពេញ"], "Banteay Meanchey": ["បន្ទាយមានជ័យ"], "Battambang": ["បាត់ដំបង"],
    "Kampong Cham": ["កំពង់ចាម"], "Kampong Chhnang": ["កំពង់ឆ្នាំង"], "Kampong Speu": ["កំពង់ស្ពឺ"],
    "Kampong Thom": ["កំពង់ធំ"], "Kampot": ["កំពត"], "Kandal": ["កណ្ដាល", "កណ្តាល"], "Kep": ["កែប"],
    "Koh Kong": ["កោះកុង"], "Kratie": ["ក្រចេះ"], "Mondulkiri": ["មណ្ឌលគិរី"],
    "Oddar Meanchey": ["ឧត្តរមានជ័យ", "ឧត្ដរមានជ័យ"], "Pailin": ["ប៉ៃលិន"], "Preah Sihanouk": ["ព្រះសីហនុ"],
    "Preah Vihear": ["ព្រះវិហារ"], "Prey Veng": ["ព្រៃវែង"], "Pursat": ["ពោធិ៍សាត់", "ពោធិសាត់", "ពោធិ៌សាត់"],
    "Ratanakiri": ["រតនគិរី"], "Siem Reap": ["សៀមរាប"], "Stung Treng": ["ស្ទឹងត្រែង"],
    "Svay Rieng": ["ស្វាយរៀង"], "Takeo": ["តាកែវ"], "Tbong Khmum": ["ត្បូងឃ្មុំ"],
}
PROV_LOOKUP = {s: k for k, v in PROVINCES.items() for s in v}
PROV_RE = "|".join(sorted(PROV_LOOKUP, key=len, reverse=True))
ANCHOR = re.compile(r"(ខេត្ត|រាជធានី|ក្រុង)\s*(" + PROV_RE + ")")
BARE = re.compile("(" + PROV_RE + r")(?!\s*\d?[A-Z])")

RESIDENCE = re.compile(r"ទីលំនៅ|រស់នៅ|ស្រុកកំណើត|អាស្រ័យ|ស្នាក់នៅ|មន្ទីរពេទ្យ|ពេទ្យ|កើតនៅ|មកពី|ស្រុកកំណើត")
ROUTE = re.compile(r"(?:ភ្នំពេញ\s*-\s*|ពី\s*|ទៅ\s*|មក\s*|ឆ្ពោះទៅ\s*|តម្រង់ទៅ\s*|និង\s*)(?:ខេត្ត|រាជធានី|ក្រុង)?\s*$")
EVENT_CUE = re.compile(r"ស្ថិតនៅ|កើតឡើង|កើតហេតុ|នៅចំណុច|ចំណុច|បណ្ដោយ|បណ្តោយ|ផ្លូវជាតិ|ទីតាំង|ផ្លូវ\s*\d|ស្ពាន")
ADMIN_SEG = re.compile(r"(ភូមិ|ឃុំ|សង្កាត់|ស្រុក|ខណ្ឌ)\s*([^\s។,៕()]{1,24})")

# Sentences giving general advice or totals are not evidence about this crash.
GENERIC = re.compile(r"កុំ|អំពាវនាវ|គួរតែ|ជាមូលហេតុចម្បង|មូលហេតុចម្បង|ផ្សព្វផ្សាយ|យុទ្ធនាការ|ស្ថិតិ|ក្នុងមួយឆ្នាំ|ប្រចាំឆ្នាំ|ប្រចាំខែ|ប្រាក់ពិន័យ|ច្បាប់ស្តីពីចរាចរណ៍")

# Period or national totals often close an article about one crash.
AGGREGATE_SENT = re.compile(r"ក្នុងរយៈពេល|រយៈពេល\s*\d|សរុប|ទូទាំងប្រទេស|ទូទាំងកម្ពុជា|ប្រចាំ|ខែមុន|ជារៀងរាល់|ក្នុងមួយថ្ងៃ|គិតចាប់ពី|បើធៀប|ស្ថិតិ|\d+\s*ករណី|\d+\s*លើក|ឆ្នាំ\s*20\d\d[^។]{0,40}(?:ស្លាប់|របួស)")
BOILERPLATE = re.compile(r"ហាមដាច់ខាត[^\n។]*[។]?|©[^\n]*|គ្មានផ្នែកណាមួយនៃអត្ថបទ.*|រក្សាសិទ្ធិគ្រប់យ៉ាង[^\n]*|សូមទស្សនារូបភាព[^\n]*|អុីម៉ែល៖[^\n]*")

CAUSES = {
    "speeding": r"(?<!ផ្លូវ)(?<!ផ្លូវជាតិ)ល្បឿនលឿន|បើកលឿន|បើកបរលឿន|បើកយ៉ាងលឿន|យ៉ាងលឿន|លឿនពេក|លឿនហួស|ល្បឿនលើស|លើសល្បឿន|ល្បឿនខ្លាំង",
    "drunk_driving": r"(?<!មិន)(?<!មិនបាន)ស្រវឹង|ជោគជាំ|ផឹកស្រា|ជាតិអាល់កុល",
    "careless_driving": r"មិនបានប្រុងប្រយ័ត្ន|មិនប្រុងប្រយ័ត្ន|ខ្វះការប្រុងប្រយ័ត្ន|ខ្វះប្រុងប្រយ័ត្ន|មិនប្រយ័ត្ន|ធ្វេសប្រហែស|ប្រមាទ",
    "wrong_way": r"បញ្ច្រាស់|បញ្ច្រាស",
    "overtaking": r"វ៉ាជែង|ប្រជែង",
    "lost_control": r"ជ្រុល|រេចង្កូត|បាត់បង់ការគ្រប់គ្រង|គ្រប់គ្រងចង្កូតមិនបាន|គ្រប់គ្រងរថយន្តមិនបាន|គ្រប់គ្រងមិនបាន",
    "brake_failure": r"(?:ដាច់|ខូច|បាក់)\s*ហ្វ្រ?ាំង|ហ្វ្រ?ាំងមិន|ហ្រ្វាំងមិន",
    "tyre_burst": r"ផ្ទុះកង់|ផ្ទុះសំបកកង់|កង់ផ្ទុះ",
    "fatigue": r"ងងុយ|ដេកលក់|អស់កម្លាំង",
    "wet_road_or_rain": r"ភ្លៀង|ផ្លូវរអិល|ផ្លូវសើម",
    "turning_or_crossing": r"បត់ស្តាំ|បត់ស្ដាំ|បត់ឆ្វេង|បត់ក្រោយ|បត់ចូល|ឆ្លងផ្លូវ|កាត់ផ្លូវ",
    "phone_use": r"លេងទូរស័ព្ទ|និយាយទូរស័ព្ទ|ប្រើទូរស័ព្ទ|កាន់ទូរស័ព្ទ",
}
VEHICLES = {
    "motorcycle": r"ម៉ូតូ",
    "car_or_light_vehicle": r"រថយន្ត|ឡាន",
    "heavy_truck": r"កុងតឺន័រ|កុងតឺន័|ឡានធំ|រថយន្តធំ|ដឹកទំនិញ|បែនដឹក|ធុនធំ|ក្រឡុកស៊ីម៉ង|ឡានដឹក|រថយន្តដឹក|ស៊ីទែន|ឡានបែន",
    "bus_or_van": r"ឡានក្រុង|រថយន្តក្រុង|ក្រុងដឹកអ្នកដំណើរ|ឡានឈ្នួល|រថយន្តឈ្នួល|មីនីប៊ីស|ហៃអេស|តាក់ស៊ី",
    "tuk_tuk": r"រ៉ឺម៉ក|រឺម៉ក|រីម៉ក|តុកតុក|ទុកទុក|កង់បី",
    "bicycle": r"ជិះកង់(?!បី)|កង់ពីរ|បុកកង់(?!បី)|កង់ធម្មតា",
    "pedestrian": r"ថ្មើរជើង|ដើរឆ្លង|ដើរកាត់|កំពុងដើរ",
    "tractor": r"គោយន្ត|ត្រាក់ទ័រ",
}
COLLISIONS = {
    "Head-on": r"បុកពីមុខ|បុកទល់មុខ|បុកគ្នាពីមុខ|បុកគ្នាចំមុខ|ទល់មុខគ្នា|បុកចំមុខ",
    "Rear-end": r"បុកពីក្រោយ|បុកពីរក្រោយ|បុកចំពីក្រោយ|បុកគូទ|បុកកន្ទុយ|បុកពីខាងក្រោយ|បុកខាងក្រោយ",
    "Side/sideswipe": r"បុកចំហៀង|បុកពីចំហៀង|ប្រលះ|កៀរ|បុកខាងចំហៀង|បុក[^។]{0,16}ពីចំហៀង",
    "Rollover": r"ក្រឡាប់",
    "Ran off road/fell": r"ធ្លាក់ចូល|ធ្លាក់ពី|ធ្លាក់ស្ពាន|ធ្លាក់ទៅ|ជ្រុលចូល|ធ្លាក់ផ្លូវ",
    "Hit fixed object": r"បុកដើមឈើ|បុកបង្គោល|បុករបង|បុកទ្រូងផ្លូវ|បុកផ្ទះ|បុកស្តង់|បុកភ្លើង|បុកជញ្ជាំង|បុកឃឿន|បុកចែកផ្លូវ|បុកស្ពាន|បុកហាង",
    "Hit pedestrian": r"បុក[^។]{0,16}(?:ថ្មើរជើង|ដើរឆ្លង|កំពុងដើរ)",
}
INTERSECTION = r"ផ្លូវប្រសព្វ|ផ្លូវបំបែក|ផ្លូវបំជា|ភ្លើងស្តុប|ភ្លើងស្ដុប|ស្តុប|កែងនឹង|កែងនិង|កែងផ្លូវ|ផ្លូវបែក"
CRASH_VERB = re.compile(r"បុក|ប៉ះ|ក្រឡាប់|ប្រលះ|កិន|គ្រោះថ្នាក់|ធ្លាក់|កៀរ|ដួល|ជ្រុល")

NEG = r"(?:មិនមាន|មិនបាន|មិនបង្ក|គ្មាន|អត់មាន|អត់|ពុំមាន|ពុំបាន|ពុំ|ឥតមាន)"
SINGLE = {"ម្នាក់": 1, "មួយនាក់": 1, "១នាក់": 1, "ពីរនាក់": 2, "បីនាក់": 3, "បួននាក់": 4, "ប្រាំនាក់": 5,
          "ប្រាំមួយនាក់": 6, "ប្រាំពីរនាក់": 7, "ប្រាំបីនាក់": 8, "ប្រាំបួននាក់": 9, "ដប់នាក់": 10}
CNT = r"(?P<n>\d{1,3}\s*នាក់|" + "|".join(sorted(SINGLE, key=len, reverse=True)) + ")"
FILL = r"(?:ភ្លាមៗ|ភ្លាម|នៅនឹងកន្លែង|នៅនិងកន្លែង|កើតហេតុ|ចំនួន|មនុស្ស|ក្នុងនោះ|ជាង|ជិត|យ៉ាងតិច|ប្រមាណ|ប្រហែល|\s)*"
ADULT = r"(?:ទៀត|ផ្សេងទៀត|ផងដែរ|បាន|ក៏|\s|ត្រូវ)*"
D1 = re.compile(r"(?:ស្លាប់|បាត់បង់ជីវិត|អស់ជីវិត)" + FILL + CNT)
D2 = re.compile(CNT + ADULT + r"(?:ស្លាប់|បាត់បង់ជីវិត|អស់ជីវិត)")
I_WORD = r"(?:រង)?របួស(?P<k>ធ្ងន់ធ្ងរ|ធ្ងន់|ស្រាល)?(?:\s*(?:-|និង)?\s*(?:ស្រាល|ធ្ងន់))?"
I1 = re.compile(I_WORD + r"(?:\s|ចំនួន|មនុស្ស|ផ្សេងទៀត|ទៀត|យ៉ាងតិច|យ៉ាង|ជាង|ជិត|ប្រមាណ|ប្រហែល)*" + CNT)
I2 = re.compile(CNT + ADULT + I_WORD)


def clean(text):
    text = ZW.sub("", text).translate(K2A).replace("ស្លា-ប់", "ស្លាប់").replace("កិ-ន", "កិន")
    for variant, standard in (("រថយន្ដ", "រថយន្ត"), ("ធន់ធំ", "ធុនធំ"), ("កុងទីន័រ", "កុងតឺន័រ"), ("កុងទឺន័រ", "កុងតឺន័រ"), ("កុងតៃន័រ", "កុងតឺន័រ"),
                              ("ថ្មើជើង", "ថ្មើរជើង"), ("ធ្វេសប្រហេស", "ធ្វេសប្រហែស")):
        text = text.replace(variant, standard)
    return text


def to_count(token):
    token = token.replace(" ", "")
    if token in SINGLE:
        return SINGLE[token]
    return int(re.match(r"\d+", token).group(0))


def safe_date(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def parse_publish(raw_line):
    s = raw_line
    m = re.search(r"(20[12]\d)-(\d{2})-(\d{2})T", s)
    if m:
        return safe_date(*m.groups())
    m = re.search(r"(" + MONTH_RE + r")\s+(\d{1,2}),\s*(20[12]\d)", s)
    if m:
        return safe_date(m.group(3), MONTHS[m.group(1)], m.group(2))
    m = re.search(r"(\d{1,2})\s*[- ]?\s*(?:ខែ\s*)?(" + MONTH_RE + r")\s*[- ]?\s*(?:ឆ្នាំ\s*)?(20[12]\d)", s)
    if m:
        return safe_date(m.group(3), MONTHS[m.group(2)], m.group(1))
    return None


def split_article(text):
    """Return (source_format, title, publish_date, body)."""
    if text.startswith("ចំណងជើង:"):
        m = re.match(r"ចំណងជើង:\s*(.*?)\s*កាលបរិច្ឆេទ:\s*(.*?)\n(.*)", text, re.S)
        if m:
            title, line, body = m.groups()
            return "Labelled article", re.sub(r"\s+", " ", title), parse_publish(line), body.replace("មាតិកាពេញលេញ:", "", 1).strip()
    first = text.split("\n", 1)[0].strip()
    pub = None
    head = text[:500]
    m = re.search(r"(20[12]\d)\.(\d{2})\.(\d{2})", head)
    if m:
        pub = safe_date(*m.groups())
    if not pub:
        m = re.search(r"(?:ផ្សាយ|ចេញផ្សាយ|កែប្រែ)[^\n]{0,24}?(\d{1,2})\s*ខែ\s*(" + MONTH_RE + r")\s*(?:ឆ្នាំ\s*)?(20[12]\d)", head)
        if m:
            pub = safe_date(m.group(3), MONTHS[m.group(2)], m.group(1))
    return "Plain text", first[:220], pub, text


DATE_RE = re.compile(r"(?:ថ្ងៃទី|ថ្ងៃ|ទី|រសៀល|ព្រឹក|ល្ងាច|យប់)\s*(\d{1,2})\s*(?:ខែ)?\s*(" + MONTH_RE + r")(?:\s*(?:ឆ្នាំ\s*)?(?:[" + KH + r"]{1,8}\s*)?(20[12]\d))?")
NUM_DATE_RE = re.compile(r"(?<![\d.])(\d{1,2})[/.\-](\d{1,2})[/.\-](20[12]\d)(?!\d)")


def find_incident_date(body, pub):
    """Prefer a date beside an event cue and never accept one after publication."""
    best, best_score = None, -99
    for m in DATE_RE.finditer(body):
        ctx = body[max(0, m.start() - 26):m.start()]
        y = m.group(3)
        inferred = False
        if not y:
            if not pub:
                continue
            y, inferred = pub.year, True
        d = safe_date(y, MONTHS[m.group(2)], m.group(1))
        if not d:
            continue
        if inferred and pub and d > pub and (d.month == 12 and pub.month == 1):
            d = safe_date(pub.year - 1, d.month, d.day)
            if not d:
                continue
        score = 0
        if re.search(r"ផ្សាយ|កែប្រែ|ចេញផ្សាយ|កាលបរិច្ឆេទ", ctx):
            score -= 6
        if re.search(r"ត្រូវនឹង|វេលា|ម៉ោង|កាលពី|យប់|ព្រឹក|រសៀល|ល្ងាច|កើត|នាទី", ctx):
            score += 3
        if not inferred:
            score += 1
        if pub:
            lag = (pub - d).days
            if lag < 0:
                score -= 8
            elif lag <= 14:
                score += 2
            elif lag > 60:
                score -= 3
        if score > best_score:
            best, best_score = d, score
    if best and best_score > -3:
        return best, "Article text"
    for m in NUM_DATE_RE.finditer(body):
        d = safe_date(m.group(3), m.group(2), m.group(1))
        if d and (not pub or 0 <= (pub - d).days <= 60):
            return d, "Article text"
    if pub:
        return pub, "Publication date (proxy)"
    return None, "None"


def find_partial_date(body):
    """Month and year for articles that never state a full date."""
    month = year = ""
    m = DATE_RE.search(body)
    if m:
        month = MONTHS[m.group(2)]
    y = re.search(r"ឆ្នាំ\s*(20[12]\d)", body)
    if y:
        year = int(y.group(1))
    return year, month


PERIOD = r"ទៀបភ្លឺ|ព្រលឹម|ភ្លឺ|ព្រឹក|ថ្ងៃត្រង់|រសៀល|ល្ងាច|យប់|អធ្រាត្រ"
TIME_RE = re.compile(r"ម៉ោង\s*[:៖]?\s*(?:ជាង|ប្រមាណ|ប្រហែល|ជិត|ខិតជិត|ពេល|នៅ)*\s*(\d{1,2})"
                     r"(?:\s*(?:និង|នឹង|:|៖|\.|-|h)\s*(\d{1,2}))?\s*(?:នាទី)?\s*(?:ជាង)?\s*(?:នៅ|ពេល)?\s*(" + PERIOD + ")?")
WORD_PERIOD = re.compile(r"(ទៀបភ្លឺ|ព្រលឹម|ព្រឹក|រសៀល|ល្ងាច|យប់)(?:មិញ|នេះ|ថ្ងៃ)")


def to_24h(h, period):
    """Return hour in 24h form, or None when am/pm cannot be determined."""
    if h > 24:
        return None
    if h > 12:
        return h % 24
    if h == 0:
        return 0
    if not period:
        return None
    if period in ("ព្រឹក", "ភ្លឺ", "ទៀបភ្លឺ", "ព្រលឹម"):
        return 0 if h == 12 else h
    if period == "ថ្ងៃត្រង់":
        return h if h >= 10 else h + 12
    if period in ("រសៀល", "ល្ងាច"):
        return 12 if h == 12 else h + 12
    if period == "អធ្រាត្រ":
        return 0 if h == 12 else h
    if period == "យប់":
        if h == 12:
            return 0
        return h if h <= 4 else h + 12
    return None


def band(hour):
    if hour is None:
        return ""
    if 5 <= hour <= 11:
        return "Morning (05-11)"
    if 12 <= hour <= 16:
        return "Afternoon (12-16)"
    if 17 <= hour <= 20:
        return "Evening (17-20)"
    return "Night (21-04)"


def find_time(body):
    ranked = []
    for m in TIME_RE.finditer(body):
        prefix = body[max(0, m.start() - 10):m.start()]
        if re.search(r"\d\s*$|រយៈពេល", prefix):
            continue
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        if mi > 59:
            mi = 0
        h24 = to_24h(h, m.group(3))
        ranked.append((0 if "វេលា" in body[max(0, m.start() - 12):m.start()] else 1, m.start(), h, mi, h24, m.group(3)))
    if ranked:
        ranked.sort(key=lambda x: (x[0], x[1]))
        _, _, h, mi, h24, _ = ranked[0]
        if h24 is not None:
            return f"{h24:02d}:{mi:02d}", band(h24), "Explicit"
        return "", "", f"Ambiguous am/pm ({h}:{mi:02d})"
    wm = WORD_PERIOD.search(body)
    if wm:
        return "", {"ទៀបភ្លឺ": "Night (21-04)", "ព្រលឹម": "Morning (05-11)", "ព្រឹក": "Morning (05-11)", "រសៀល": "Afternoon (12-16)",
                    "ល្ងាច": "Evening (17-20)", "យប់": "Night (21-04)"}[wm.group(1)], "Period word only"
    return "", "", "None"


def find_location(title, body):
    text = title + " ។ " + body
    scores = Counter()
    pos = {}
    for m in ANCHOR.finditer(text):
        name = PROV_LOOKUP[m.group(2)]
        before = text[max(0, m.start() - 130):m.start()]
        near = text[max(0, m.start() - 45):m.start()]
        s = 1
        if re.search(r"(ឃុំ|សង្កាត់|ស្រុក|ខណ្ឌ)[^។]*$", before):
            s += 4
        if EVENT_CUE.search(text[max(0, m.start() - 220):m.start()]):
            s += 2
        if m.start() < 220 + len(title):
            s += 2
        if RESIDENCE.search(near):
            s -= 7
        if ROUTE.search(near[-14:]):
            s -= 3
        scores[name] += s
        if s >= 3 and (name not in pos or s > pos[name][0]):
            pos[name] = (s, m.start())
    conf, province = "", ""
    if scores and scores.most_common(1)[0][1] > 0:
        province = scores.most_common(1)[0][0]
        conf = "High" if scores[province] >= 7 else "Medium"
    elif "ខណ្ឌ" in body:
        province, conf = "Phnom Penh", "Medium"
    else:
        bare = Counter(PROV_LOOKUP[x] for x in BARE.findall(text))
        if bare:
            province, conf = bare.most_common(1)[0][0], "Low"

    district = commune = village = ""
    win = ""
    if province in pos:
        win = text[max(0, pos[province][1] - 150):pos[province][1]]
    if not win:
        for m in ADMIN_SEG.finditer(text):
            if not RESIDENCE.search(text[max(0, m.start() - 40):m.start()]):
                win = text[m.start():m.start() + 150]
                break
    for m in ADMIN_SEG.finditer(win):
        kind, name = m.group(1), m.group(2).strip()
        name = re.split(r"\s*(?:ភូមិ|ឃុំ|សង្កាត់|ស្រុក|ខណ្ឌ|ក្រុង|ខេត្ត|រាជធានី)", name)[0].strip()
        if not name:
            continue
        if kind in ("ស្រុក", "ខណ្ឌ"):
            district = f"{kind}{name}"
        elif kind in ("ឃុំ", "សង្កាត់"):
            commune = f"{kind}{name}"
        else:
            village = f"{kind}{name}"
    return province, conf, district, commune, village


def find_road(text):
    m = re.search(r"ផ្លូវជាតិ(?:លេខ)?\s*(\d{1,3})\s*([A-Za-z]?)(?![A-Za-z])", text)
    km = re.search(r"(?:គីឡូម៉ែត្រ|គ\.ម|គមទី)\s*(?:លេខ|ទី|ទិ)?\s*(\d{1,3})", text)
    km_val = km.group(1) if km else ""
    if m:
        return "National road", f"NR{int(m.group(1))}{m.group(2).upper()}", km_val
    if "ផ្លូវល្បឿនលឿន" in text or "ផ្លូវជាតិល្បឿនលឿន" in text:
        return "Expressway", "Phnom Penh-Sihanoukville expressway" if "សីហនុ" in text else "Expressway", km_val
    m = re.search(r"ផ្លូវខេត្ត\s*(?:លេខ)?\s*(\d+\S*)", text)
    if m:
        return "Provincial road", m.group(1), km_val
    m = re.search(r"ផ្លូវ(?:ទីក្រុង|លេខ)?\s*(\d{1,4}[A-Za-z]?)(?!\s*ម៉ែត្រ)(?!\d)", text)
    if m:
        return "City street", f"Street {m.group(1)}", km_val
    if re.search(r"ផ្លូវលំ|ផ្លូវដី|ផ្លូវកៅស៊ូ|ផ្លូវបេតុង", text):
        return "Local road", "", km_val
    if re.search(r"ផ្លូវ|វិថី|ស្ពាន", text):
        return "Unclassified", "", km_val
    return "Unknown", "", km_val


def sentences(text):
    return [s for s in re.split(r"[។៕\n]+", text) if s.strip()]


def negated(s, word):
    if not re.search(NEG + r"[^។]{0,28}(?:" + word + ")", s):
        return False
    return not re.search(r"(?:គ្មាន|មិនមាន)(?:មួក|ស្លាក|ផ្លាក|អត្ត)", s)


def death_count(s):
    if negated(s, "ស្លាប់|បាត់បង់ជីវិត"):
        return None, ""
    best, ev = None, ""
    for rx in (D1, D2):
        for m in rx.finditer(s):
            n = to_count(m.group("n"))
            if n <= 100 and (best is None or n > best):
                best, ev = n, s[max(0, m.start() - 20):m.end() + 12].strip()
    return best, ev


def injury_counts(s):
    found = {}
    ev = ""
    if negated(s, "របួស"):
        return found, ev
    for rx in (I1, I2):
        for m in rx.finditer(s):
            n = to_count(m.group("n"))
            if n > 150:
                continue
            kind = m.group("k")
            whole = m.group(0)
            if kind in ("ធ្ងន់", "ធ្ងន់ធ្ងរ") and not re.search(r"ធ្ងន់[^\d]{0,8}ស្រាល", whole):
                key = "severe"
            elif kind == "ស្រាល":
                key = "minor"
            else:
                key = "general"
            found[key] = max(found.get(key, 0), n)
            ev = ev or s[max(0, m.start() - 20):m.end() + 12].strip()
    return found, ev


def find_casualties(title, body):
    """Counts come from the title if stated, otherwise the first sentence that gives one."""
    all_sents = [s for s in sentences(body) if not GENERIC.search(s)]
    sents = [s for s in all_sents if not AGGREGATE_SENT.search(s)]
    title_ok = "" if AGGREGATE_SENT.search(title) else title
    joined = "។".join(sents)

    deaths, fatal_ev = death_count(title_ok)
    if deaths is None:
        for s in sents:
            deaths, fatal_ev = death_count(s)
            if deaths is not None:
                break
    fatal_word = None
    for s in [title_ok] + sents:
        if negated(s, "ស្លាប់|បាត់បង់ជីវិត"):
            continue
        fatal_word = re.search(r"ស្លាប់|បាត់បង់ជីវិត|អស់ជីវិត|មរណភាព|(?:^|[\s(])សព(?=ជន|\s|ត្រូវ|និង|បុរស|ស្ត្រី|របស់)", s)
        if fatal_word:
            fatal_ev = fatal_ev or s[max(0, fatal_word.start() - 20):fatal_word.end() + 16].strip()
            break

    inj, inj_ev = injury_counts(title_ok)
    if not inj:
        for i, s in enumerate(sents):
            found, ev = injury_counts(s)
            if found:
                inj, inj_ev = found, ev
                if i + 1 < len(sents):
                    for key, val in injury_counts(sents[i + 1])[0].items():
                        inj.setdefault(key, val)
                break
    sev, minor, general = inj.get("severe"), inj.get("minor"), inj.get("general")
    injured = None
    if inj:
        injured = max((sev or 0) + (minor or 0), general or 0)

    injury_word = None
    for s in [title_ok] + sents:
        if negated(s, "របួស"):
            continue
        injury_word = re.search(r"របួស", s)
        if injury_word:
            inj_ev = inj_ev or s[max(0, injury_word.start() - 20):injury_word.end() + 16].strip()
            break
    no_injury = bool(re.search(NEG + r"[^។]{0,30}របួស|សំណាងល្អ[^។]{0,30}(?:គ្មាន|មិនមាន)", joined))
    many = bool(re.search(r"របួស[^។]{0,12}(?:ជាច្រើន|ច្រើននាក់|រាប់សិប|រាប់រយ)|(?:ច្រើននាក់|រាប់សិបនាក់|រាប់រយនាក់)[^។]{0,10}របួស", title + "។" + joined))

    deaths_known = deaths is not None
    if deaths is None and fatal_word:
        deaths = 1
    if deaths:
        severity = "Fatal"
    elif injury_word or injured:
        severity = "Injury"
    elif no_injury or "ខូចខាត" in joined:
        severity = "Property damage only"
    else:
        severity = "Not stated"
    note = []
    if fatal_word and not deaths_known:
        note.append("death count assumed 1 (no number stated)")
    if injury_word and injured is None:
        note.append("injury count not stated")
    if many:
        note.append("'many' injured reported")
    return severity, deaths, sev, minor, injured, fatal_ev, inj_ev, "; ".join(note)


def find_causes(title, body):
    sents = [s for s in sentences(title + "\n" + body) if not GENERIC.search(s)]
    hits, evidence = [], ""
    for name, pat in CAUSES.items():
        for s in sents:
            m = re.search(pat, s)
            if m:
                hits.append(name)
                evidence = evidence or s[max(0, m.start() - 24):m.end() + 16].strip()
                break
    run = next((s for s in sents if re.search(r"រត់គេច|គេចខ្លួន", s) and not re.search(r"មិនបាន(?:រត់)?គេច|មិន(?:រត់)?គេច", s)), None)
    helmet_any = any(re.search(r"មួកសុវ", s) for s in sents)
    no_helmet = any(re.search(r"(?:គ្មាន|មិន(?:បាន)?ពាក់|អត់ពាក់|ពុំបានពាក់|មិនពាក់)[^។]{0,12}មួកសុវ", s) for s in sents)
    return hits, evidence, bool(run), ("No helmet" if no_helmet else "Helmet mentioned" if helmet_any else "")


REPORT_TITLE = re.compile(r"ស្ថិតិ|របាយការណ៍|អត្រាស្លាប់|\d+\s*ខែ\s*ដើមឆ្នាំ|ឆមាស|ត្រីមាស|ប្រចាំឆ្នាំ|ប្រចាំខែ|ប្រចាំសប្តាហ៍|ករណីសរុប|រយៈពេល|ទូទាំងប្រទេស|ចរាចរណ៍ខែមុន|ថ្ងៃចុងក្រោយ|មួយថ្ងៃម្សិលមិញ|ចរាចរណ៍ម្សិលមិញ|ក្នុងមួយថ្ងៃ|\d+\s*សប្តាហ៍|សម្លាប់មនុស្សជិត|ស្លាប់ជិត\s*\d{2,}|អំឡុងចូលឆ្នាំ|អំឡុងពេលចូលឆ្នាំ|សងចូលឆ្នាំ|ភ្ជុំបិណ្ឌ|\d+\s*ថ្ងៃ\s*ចាប់ពី|គ្រោះថ្នាក់ចរាចរណ៍(?:នៅ|កាលពី)?ថ្ងៃ(?:ទី)?\s*\d+[^។]{0,14}ស្លាប់|ស្លាប់ដោយគ្រោះថ្នាក់ចរាចរណ៍កាលពីថ្ងៃ\s*\d")
FOLLOWUP_TITLE = re.compile(r"អយ្យការ|តុលាការ|សាលាដំបូង|សាលាឧទ្ធរណ៍|ចោទប្រកាន់|ចូលខ្លួន|ឃុំខ្លួន|ផ្តន្ទាទោស|កាត់ទោស|ជាប់ពន្ធនាគារ|ជាប់គុក|សំណង|ឧបត្ថម្ភ|ចូលបំភ្លឺ|ចំណាត់ការ|ដោះលែង|សួរសុខទុក្ខ|រំលែកទុក្ខ|រំលែកមរណទុក្ខ|ចូលរួមរំលែក|ថវិកា|បុណ្យសព|ដាក់ពន្ធនាគារ|កាត់ប័ណ្ណ|ស៊ើបអង្កេត|ស៊ើបករណី|ផាកពិន័យ")
FEATURE_TITLE = re.compile(r"បទយកការណ៍|បទសម្ភាសន៍|សម្ភាស|យុទ្ធនាការ|សិក្ខាសាលា|វគ្គបណ្តុះបណ្តាល|អំពាវនាវ|ស្នើរដ្ឋាភិបាល|វិធានការ|គោលនយោបាយ|ច្បាប់ចរាចរណ៍|សុវត្ថិភាពចរាចរណ៍|សុវត្ថិភាពផ្លូវថ្នល់|ការយល់ដឹង|ចុះពិនិត្យទីតាំង|អនុវត្តច្បាប់")
OFF_TOPIC = re.compile(r"បោះឆ្នោត")
FOREIGN = re.compile(r"^(?:ថៃ|បរទេស|ចិន|កូរ៉េ\S*|វៀតណាម|អន្តរជាតិ)\s*៖|ប្រទេស(?:ថៃ|ចិន|ឥណ្ឌា|វៀតណាម|កូរ៉េ|ឡាវ|ជប៉ុន|កាមេរូន|អ៊ីរ៉ង់|ម៉ាឡេស៊ី)|អ៊ីរ៉ង់|អ៊ីរ៉ាក់|ប៉ាគីស្ថាន|ឥណ្ឌូណេស៊ី|ឥណ្ឌូនេស៊ី|ហ្វីលីពីន|នីហ្សេរីយ៉ា|អាហ្រ្វិក|ម៉ិកស៊ិក|ប្រេស៊ីល|នេប៉ាល់|ពលករខ្មែរ|ពលករកម្ពុជា|នៅថៃ|ក្នុងថៃ")
CELEBRITY = re.compile(r"តារា|Influencer|អតីតក្រុម|សមាជិកក្រុម|កីឡាករ|BLACKPINK|អ្នកប្រដាល់|ជម្រើសជាតិ")


def classify(title, body, province, time_status):
    head = body[:220]
    has_clock = time_status == "Explicit" or time_status.startswith("Ambiguous")
    has_scene = "ស្ថិតនៅ" in body or bool(re.search(r"(?:ឃុំ|សង្កាត់)[^។]{0,40}(?:ស្រុក|ខណ្ឌ)", body))
    if not CRASH_VERB.search(title + body) or (OFF_TOPIC.search(title) and not re.search(r"បុក|ក្រឡាប់", title)):
        return "Off-topic"
    if REPORT_TITLE.search(title) or re.search(r"ចំនួន\s*(?:\d+|ពីរ|បី|បួន|ប្រាំ)\s*ករណី", body[:700]) or (re.search(r"ទូទាំងប្រទេស", head) and re.search(r"\d+\s*(?:ករណី|លើក)", head)):
        return "Statistics/aggregate"
    if FOREIGN.search(title) or FOREIGN.search(head) and "ជនជាតិ" not in head:
        return "Foreign/celebrity news"
    if CELEBRITY.search(title) and not province:
        return "Foreign/celebrity news"
    if FOLLOWUP_TITLE.search(title):
        return "Follow-up/legal"
    if FEATURE_TITLE.search(title) and not (has_clock and has_scene):
        return "Feature/policy"
    return "Crash report"


REWRITE_STRONG = re.compile(r"យោងតាមសាក្សីដែលឃើញហេតុការណ៍ផ្ទាល់ភ្នែក|សភាពនៅកន្លែងកើតហេតុ|បាក់បែកឆ្អឹងជាច្រើនកន្លែង|ខ្ទេចខ្ទីគ្មានសល់|បានដេកដួល|^ពេលវេលា\s*:|ពេលវេលា\s*:\s*មិនបានបញ្ជាក់")


def text_provenance(text):
    if re.search(r"^អត្ថបទនេះ|នេះគឺជាសេចក្តីសង្ខេប|នេះជាការរៀបរាប់ឡើងវិញ", text) or len(re.findall(r"^(?:មូលហេតុ|លទ្ធផល|ទីតាំង|ពេលវេលា)\s*៖", text, re.M)) >= 2:
        return "Suspected AI summary/rewrite"
    if REWRITE_STRONG.search(text):
        return "Suspected AI summary/rewrite"
    if text.startswith("ករណីទី") or re.search(r"ករណីទី\s*\d", text[:260]):
        return "Split from multi-crash article"
    return "Appears original"


def source_hint(text):
    for pat, name in ((r"khmernews\.news", "khmernews.news"), (r"ស៊ីស៊ីអាយអឹម|VOD គឺជា", "VOD (CCIM)"), (r"ប្រភព៖\s*freshnews|Fresh News", "Fresh News"), (r"©\s*2016", "Unnamed site (c) 2016")):
        if re.search(pat, text, re.I):
            return name
    return ""


PLATE = re.compile(r"\b\d?[A-Z]{1,3}[-. ]?\d{4}\b")


def normalise_for_match(body):
    return re.sub(rf"[^{KH}0-9A-Za-z]+", "", body)


def shingles(s, k=5):
    return {s[i:i + k] for i in range(max(1, len(s) - k + 1))}


def link_duplicates(recs, bodies):
    """Group rows that report one crash: near-identical text, or shared plates on nearby dates."""
    n = len(recs)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    shs = [shingles(normalise_for_match(b)) for b in bodies]
    plates = [{p.replace("-", "").replace(".", "").replace(" ", "") for p in PLATE.findall(b)} for b in bodies]
    dates = [date.fromisoformat(r["incident_date"]) if r["incident_date"] else None for r in recs]

    def conflict(i, j):
        if plates[i] and plates[j] and not plates[i] & plates[j]:
            return True
        return bool(dates[i] and dates[j] and abs((dates[i] - dates[j]).days) > 3)

    index = {}
    for i, s in enumerate(shs):
        for g in s:
            index.setdefault(g, []).append(i)
    overlap = Counter()
    for g, ids in index.items():
        if 2 <= len(ids) <= 25:
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    overlap[(ids[a], ids[b])] += 1
    for (i, j), c in overlap.items():
        if c >= 30:
            jac = len(shs[i] & shs[j]) / len(shs[i] | shs[j])
            if jac >= 0.6 and not conflict(i, j):
                parent[find(i)] = find(j)

    by_plate = {}
    for i, ps in enumerate(plates):
        for p in ps:
            by_plate.setdefault(p, []).append(i)
    for ids in by_plate.values():
        if 2 <= len(ids) <= 8:
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    i, j = ids[a], ids[b]
                    if dates[i] and dates[j] and abs((dates[i] - dates[j]).days) <= 3:
                        parent[find(i)] = find(j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def build_records(src):
    ws = load_workbook(src, read_only=True).worksheets[0]
    rows = [{"Filename": a, "Crash_Description": b} for a, b in ws.iter_rows(min_row=2, max_col=2, values_only=True) if a]
    recs, bodies = [], []
    for r in rows:
        text = clean(r["Crash_Description"])
        fmt, title, pub, body = split_article(text)
        provenance, source = text_provenance(text), source_hint(text)
        body = BOILERPLATE.sub(" ", body)
        inc, inc_src = find_incident_date(body, pub)
        t24, tband, tstatus = find_time(body)
        province, pconf, district, commune, village = find_location(title, body)
        road_type, road_name, km = find_road(title + " " + body)
        severity, deaths, sev, minor, injured, fatal_ev, inj_ev, cas_note = find_casualties(title, body)
        causes, cause_ev, hit_run, helmet = find_causes(title, body)
        scene = re.sub(r"(?:រថយន្ត|ឡាន)(?:សង្គ្រោះ|ពេទ្យ|ប៉ូលិស|នគរបាល)\S*", " ", title + " " + body)
        vehicles = [k for k, p in VEHICLES.items() if re.search(p, scene)]
        collisions = [k for k, p in COLLISIONS.items() if re.search(p, title + body)]
        rtype = classify(title, body, province, tstatus)
        year, month = (inc.year, inc.month) if inc else find_partial_date(body)
        if not inc and (year or month):
            inc_src = "Partial (year/month only)"
        if re.search(r"បុក|ប៉ះ", title + body) and not collisions:
            collisions = ["Collision (type not stated)"]
        recs.append({
            "filename": r["Filename"], "doc_id": int(re.search(r"\d+", r["Filename"]).group(0)),
            "record_type": rtype, "text_provenance": provenance, "source_hint": source, "source_format": fmt, "title": title,
            "publish_date": pub, "incident_date": inc, "incident_date_source": inc_src,
            "year": year, "month": month, "day_of_week": inc.strftime("%A") if inc else "",
            "incident_time": t24, "time_of_day": tband, "time_status": tstatus,
            "province": province, "province_confidence": pconf, "district": district,
            "commune": commune, "village": village, "road_type": road_type, "road_name": road_name, "km_marker": km,
            "intersection": int(bool(re.search(INTERSECTION, title + body))),
            "severity": severity, "deaths": deaths, "injuries_severe": sev, "injuries_minor": minor,
            "injuries_total": injured, "casualty_note": cas_note,
            "collision_type": "; ".join(collisions), "vehicles_involved": "; ".join(vehicles),
            **{f"veh_{k}": int(k in vehicles) for k in VEHICLES},
            "stated_factors": "; ".join(causes), **{f"factor_{k}": int(k in causes) for k in CAUSES},
            "hit_and_run": int(hit_run), "helmet_status": helmet,
            "fatality_evidence": fatal_ev, "injury_evidence": inj_ev, "factor_evidence": cause_ev,
            "Crash_Description": r["Crash_Description"],
        })
        bodies.append(body)

    for r in recs:
        r["incident_date"] = r["incident_date"].isoformat() if r["incident_date"] else ""
    for gid, group in enumerate(link_duplicates(recs, bodies), 1):
        best = max(group, key=lambda i: (recs[i]["record_type"] == "Crash report", recs[i]["text_provenance"] == "Appears original", len(bodies[i])))
        for i in group:
            recs[i]["event_id"] = f"E{gid:04d}"
            recs[i]["is_primary_record"] = int(i == best)
            recs[i]["duplicate_of"] = recs[best]["filename"] if i != best else ""
            recs[i]["duplicate_group_size"] = len(group)

    for r in recs:
        inc = date.fromisoformat(r["incident_date"]) if r["incident_date"] else None
        r["incident_date"] = inc
        reasons = []
        if r["record_type"] == "Crash report":
            if not r["province"]:
                reasons.append("province missing")
            elif r["province_confidence"] == "Low":
                reasons.append("province low confidence")
            if r["incident_date_source"] != "Article text":
                reasons.append("date not from article text")
            if r["severity"] == "Not stated":
                reasons.append("severity not stated")
            if r["publish_date"] and inc and abs((r["publish_date"] - inc).days) > 30:
                reasons.append("incident far from publish date")
            if (r["deaths"] or 0) >= 10 or (r["injuries_total"] or 0) >= 25:
                reasons.append("large casualty count, verify")
            if r["text_provenance"] != "Appears original":
                reasons.append("text may not be the original article")
        r["needs_review"] = int(bool(reasons))
        r["review_reason"] = "; ".join(reasons)
        r["analysis_ready"] = int(r["record_type"] == "Crash report" and r["is_primary_record"] == 1 and r["text_provenance"] == "Appears original")
    return recs


COLUMN_ORDER = [
    "filename", "doc_id", "analysis_ready", "record_type", "text_provenance", "needs_review", "review_reason",
    "event_id", "is_primary_record", "duplicate_of", "duplicate_group_size", "source_hint", "source_format", "title",
    "publish_date", "incident_date", "incident_date_source", "year", "month", "day_of_week",
    "incident_time", "time_of_day", "time_status", "province", "province_confidence", "district", "commune", "village",
    "road_type", "road_name", "km_marker", "intersection", "severity", "deaths", "injuries_severe", "injuries_minor",
    "injuries_total", "casualty_note", "collision_type", "vehicles_involved", *[f"veh_{k}" for k in VEHICLES],
    "stated_factors", *[f"factor_{k}" for k in CAUSES], "hit_and_run", "helmet_status",
    "fatality_evidence", "injury_evidence", "factor_evidence", "Crash_Description",
]
GROUPS = [("Identity and data quality", 14, "1F3A5F"), ("When", 9, "2E6F57"), ("Where", 9, "7A4E2D"),
          ("Severity", 6, "8C2F39"), ("Crash and vehicles", 2 + len(VEHICLES), "4B4E8C"),
          ("Stated factors", 1 + len(CAUSES) + 2, "5B5B5B"), ("Evidence and source text", 4, "3D3D3D")]
WIDTHS = {"title": 48, "review_reason": 34, "text_provenance": 26, "record_type": 21, "Crash_Description": 80, "collision_type": 26,
          "vehicles_involved": 30, "stated_factors": 34, "casualty_note": 34, "fatality_evidence": 38, "injury_evidence": 38,
          "factor_evidence": 38, "province": 18, "district": 18, "commune": 20, "village": 16, "incident_date_source": 22,
          "publish_date": 12, "incident_date": 12, "filename": 19, "time_status": 18, "road_name": 16, "road_type": 15, "time_of_day": 17}

DICTIONARY = [
    ("filename", "Original row name", "Join key back to the source workbook."),
    ("doc_id", "Number taken from the filename", "1,074 rows use IDs 1-1147, so 73 IDs are absent from the source. It is not chronological."),
    ("analysis_ready", "1 = crash report, first record of its crash, text appears original", "Filter on this for counts, charts and modeling."),
    ("record_type", "Crash report, Statistics/aggregate, Follow-up/legal, Foreign/celebrity news, Feature/policy, Off-topic", "Only Crash report rows describe one crash in Cambodia."),
    ("text_provenance", "Appears original, Suspected AI summary/rewrite, Split from multi-crash article", "A suspicion based on phrasing, not proof. Causes and severity in these rows may not match the real event."),
    ("needs_review / review_reason", "1 = a person should check this crash report, and why", "Sort by this when correcting data by hand."),
    ("event_id", "Same ID = same crash", "Matched on near-identical text, or shared plate numbers within 3 days. Plates are not stored here. Reports of one crash by different outlets with no shared plate can still be missed."),
    ("is_primary_record / duplicate_of / duplicate_group_size", "Which row represents the crash", "Count crashes with is_primary_record = 1."),
    ("source_hint", "Outlet, only where the text names it", "Blank for most rows: the source file has no outlet or URL column."),
    ("source_format", "Labelled article or Plain text", "Two scraping formats. Do not use as a model feature."),
    ("title", "Headline, or first line for Plain text rows", ""),
    ("publish_date", "Parsed from about 30 date formats", "Often blank for Plain text rows."),
    ("incident_date / incident_date_source", "Crash date and how it was found", "'Publication date (proxy)' is an estimate, usually within a few days. 'Partial' has year or month only."),
    ("year / month / day_of_week", "Derived from incident_date", "Year counts reflect collection effort, not the true trend."),
    ("incident_time / time_of_day / time_status", "24h time and period", "Blank when am/pm cannot be determined ('Ambiguous'). Never guessed."),
    ("province / province_confidence", "Crash location, not home address, hospital or plate", "High = full administrative chain. Medium = named once. Low = weak mention."),
    ("district / commune / village", "Khmer text as written", "Spelling is not standardised, so clean before grouping."),
    ("road_type / road_name / km_marker", "Road class, name and kilometre post", "There are no GPS coordinates in the source."),
    ("intersection", "1 = junction or traffic light mentioned", "Keyword based."),
    ("severity", "Fatal, Injury, Property damage only, Not stated", "Highest outcome the article reports."),
    ("deaths", "Deaths in this crash", "Title first, then the first sentence with a number. Later deaths can be missed. Assumed 1 when death is stated with no number, see casualty_note."),
    ("injuries_severe / injuries_minor / injuries_total", "Injured people", "Blank means no number was stated, not zero."),
    ("collision_type", "Multi-label, separated by ;", "Most reports only say 'hit', giving 'Collision (type not stated)'."),
    ("vehicles_involved / veh_*", "Vehicles and road users named in the article", "Multi-label. A vehicle only mentioned in passing can appear."),
    ("stated_factors / factor_*", "Contributing factors the article states", "Reporter or witness claims, not investigated causes. 0 means not mentioned, not ruled out."),
    ("hit_and_run", "1 = driver fled", ""),
    ("helmet_status", "No helmet, Helmet mentioned, or blank", "Rarely reported: blank does not mean no helmet."),
    ("fatality_evidence / injury_evidence / factor_evidence", "Short Khmer snippet behind the value", "Use to verify a row in seconds."),
    ("Crash_Description", "Original text, unchanged", "Contains victim names and plates, and third-party copyrighted text. Keep internal. Do not publish."),
]


def write_workbook(recs, dst, validation=()):
    wb = Workbook()
    ws = wb.active
    ws.title = "Accidents"
    ws.append(COLUMN_ORDER)
    for r in recs:
        ws.append([None if r[c] == "" else r[c] for c in COLUMN_ORDER])
    col = 1
    for _, span, colour in GROUPS:
        for _ in range(span):
            cell = ws.cell(row=1, column=col)
            cell.fill = PatternFill("solid", fgColor=colour)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            col += 1
    assert col - 1 == len(COLUMN_ORDER)
    for i, name in enumerate(COLUMN_ORDER, 1):
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS.get(name, 12)
        if name in ("publish_date", "incident_date"):
            for row in range(2, ws.max_row + 1):
                ws.cell(row=row, column=i).number_format = "yyyy-mm-dd"
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions

    d = wb.create_sheet("Data Dictionary")
    d.append(["Column", "Meaning", "How to read it"])
    for row in DICTIONARY:
        d.append(list(row))
    q = wb.create_sheet("Data Quality")
    ready = [r for r in recs if r["analysis_ready"]]
    q.append(["Measure", "Rows"])
    q.append(["Rows in source", len(recs)])
    for key in ("record_type", "text_provenance", "source_hint"):
        q.append([])
        q.append([key, "Rows"])
        for name, n in Counter(r[key] or "(not identified)" for r in recs).most_common():
            q.append([name, n])
    q.append([])
    q.append(["Duplicate rows (same crash reported again)", sum(1 for r in recs if not r["is_primary_record"])])
    q.append(["Crash reports needing review", sum(r["needs_review"] for r in recs)])
    q.append(["analysis_ready rows", len(ready)])
    if validation:
        q.append([])
        q.append(["Manual validation, independent random sample of crash reports", "Correct", "Checked", "Accuracy"])
        for name, ok, n in validation:
            q.append([name, ok, n, round(ok / n, 3)])
    for sheet, widths in ((d, (42, 62, 92)), (q, (62, 10, 10, 10))):
        for i, w in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(i)].width = w
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in d[1] + q[1]:
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
        cell.font = Font(bold=True, color="FFFFFF")
    d.freeze_panes = "A2"
    wb.save(dst)


# Hand-checked 2026-11-01 on 20 randomly drawn crash reports not used to write the rules.
VALIDATION = [
    ("record_type", 20, 20), ("severity", 20, 20), ("stated factors", 19, 20), ("province (1 blank, 0 wrong)", 19, 20),
    ("incident date (2 blank, 0 wrong)", 18, 20), ("death and injury counts", 16, 20), ("vehicles (before spelling fixes)", 14, 20),
]

if __name__ == "__main__":
    write_workbook(build_records(sys.argv[1]), sys.argv[2], VALIDATION)
