// Builds presentation/Cambodia_Road_Crash_Portal.pptx from presentation/deck_data.json
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const md = require("react-icons/md");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const ROOT = "/home/virak/Desktop/modeling";
const OUT = path.join(ROOT, "presentation", "Cambodia_Road_Crash_Portal.pptx");
const D = JSON.parse(fs.readFileSync(path.join(ROOT, "presentation", "deck_data.json"), "utf8"));

const THEME = {
  name: "Road Safety",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1F2328", lt1: "FFFFFF", dk2: "4A525C", lt2: "F2F3F5",
    accent1: "F2A900", accent2: "D9480F", accent3: "2F6F8F", accent4: "9AA3AD", accent5: "3C8D5A", accent6: "C7CCD2",
    hlink: "2F6F8F", folHlink: "6B4FA0",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Where and when are road crashes reported in Cambodia?";
pres.subject = "Final project: spatio-temporal data portal";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const W = 13.333, H = 7.5, M = 0.6;

// ---------------- Layouts ----------------
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.2, w: 10.6, h: 1.9, fontSize: 40, bold: true,
      color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.35, w: 10.6, h: 1.1, fontSize: 18,
      color: C.accent6, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.85, fontSize: 32,
      bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "Cambodia Road Crash Portal · Final project", options: { x: M, y: H - 0.45, w: 6, h: 0.3, fontSize: 10,
      color: C.text2, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.6, y: H - 0.45, w: 0.6, h: 0.3, fontSize: 10, color: C.text2, align: "right" },
});
pres.defineSlideMaster({
  title: "CONTENT_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.85, fontSize: 32,
      bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - M - 0.6, y: H - 0.45, w: 0.6, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
});

// ---------------- Helpers ----------------
async function icon(Comp, color = "#" + HEX.dk1) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function iconCircle(slide, Comp, x, y, d = 0.62, name = "icon") {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: C.accent1 }, line: { type: "none" }, objectName: name + " circle" });
  const pad = d * 0.2;
  slide.addImage({ data: await icon(Comp), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad, objectName: name,
    altText: name });
}
const text = (slide, value, opts) => slide.addText(value, { isTextBox: true, margin: 0, color: C.text1, fontSize: 16, ...opts });
function card(slide, x, y, w, h, name, fill = C.background2) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" },
    objectName: name });
}
function stat(slide, value, label, x, y, w, color = C.text1, size = 54) {
  text(slide, value, { x, y, w, h: 0.95, fontSize: size, bold: true, color, fontFace: THEME.headFontFace, valign: "bottom" });
  text(slide, label, { x, y: y + 1.0, w, h: 0.75, fontSize: 14, color: C.text2, valign: "top" });
}
// Chart styling shared by every chart (fresh object per call: pptxgenjs mutates options).
function chartBase(extra = {}) {
  return {
    catAxisLabelColor: HEX.dk2, valAxisLabelColor: HEX.dk2, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 12, dataLabelFontFace: "+mn-lt", dataLabelFontSize: 12,
    dataLabelColor: HEX.dk1, valGridLine: { color: "E3E5E8", size: 0.75 }, catGridLine: { style: "none" },
    catAxisLineShow: true, valAxisLineShow: false, legendFontFace: "+mn-lt", legendFontSize: 12, legendColor: HEX.dk2,
    titleFontFace: "+mn-lt", titleFontSize: 14, titleColor: HEX.dk1, showTitle: true, ...extra,
  };
}
const fmt = (v, d = 0) => Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v) => `${Math.round(v * 100)}%`;

(async () => {
  const h1a = D.h1a, h1b = D.h1b, h2 = D.h2, fc = D.forecast, r = D.rare;
  const covShare = D.coverage.news.reduce((a, b) => a + b, 0) / D.coverage.official.reduce((a, b) => a + b, 0);

  // 1. Title ------------------------------------------------------------------------------
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Opening" });
  s.addText("Where and when are road crashes reported in Cambodia?", { placeholder: "title" });
  s.addText("A spatio-temporal data portal built from Khmer-language news, the 2019 census and World Bank data for ASEAN",
    { placeholder: "body" });
  await iconCircle(s, md.MdTwoWheeler, M, 0.9, 0.95, "motorcycle icon");
  text(s, "Final project defence · November 2026", { x: M, y: 6.45, w: 8, h: 0.4, fontSize: 14, color: C.accent6 });
  s.addNotes("Our project asks where and when road crashes are reported in Cambodia. We built a live portal from three kinds of data: " +
    "crash reports we extracted from Khmer-language news, the 2019 census with province boundaries, and World Bank indicators for the 11 ASEAN members. " +
    "The short answer we will defend: the news data shows where journalists look as much as where crashes happen, and we measured how much.");

  // 1b. Table of contents ---------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Opening" });
  s.addText("Contents", { placeholder: "title" });
  const contents = [
    [md.MdHelpOutline, "Question and data", "Research question, three hypotheses, four sources and the portal", "Slides 3–5"],
    [md.MdLightbulb, "Findings", "Six findings: fatal share, coverage, ASEAN, time series, rare events", "Slides 6–11"],
    [md.MdFactCheck, "Methods and ethics", "Every course week, feature selection by rule, and what the data cannot see", "Slides 12–14"],
    [md.MdFlag, "Conclusion", "What we found and the next steps", "Slide 15"],
  ];
  for (let i = 0; i < contents.length; i++) {
    const [Ic, name, desc, pages] = contents[i];
    const y = 1.5 + i * 1.3;
    card(s, M, y, W - 2 * M, 1.1, `contents row ${i + 1}`);
    text(s, String(i + 1), { x: M + 0.3, y, w: 0.6, h: 1.1, fontSize: 32, bold: true, color: C.accent2, valign: "middle" });
    await iconCircle(s, Ic, M + 1.05, y + 0.22, 0.66, `${name} icon`);
    text(s, name, { x: M + 2.0, y: y + 0.14, w: 7.2, h: 0.45, fontSize: 20, bold: true });
    text(s, desc, { x: M + 2.0, y: y + 0.58, w: 7.2, h: 0.4, fontSize: 14, color: C.text2 });
    text(s, pages, { x: W - M - 2.3, y, w: 2.0, h: 1.1, fontSize: 16, bold: true, color: C.text2, align: "right", valign: "middle" });
  }
  s.addNotes("Here is the route through the talk: first the question and the data, then six findings, then the methods and ethics behind them, and finally what we conclude and what we would do next.");

  // 2. Question and hypotheses -----------------------------------------------------------
  pres.addSection({ title: "Question and data" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Question and data" });
  s.addText("One question, three testable hypotheses", { placeholder: "title" });
  card(s, M, 1.5, 4.7, 5.1, "question card", C.text1);
  await iconCircle(s, md.MdHelpOutline, M + 0.4, 1.9, 0.7, "question icon");
  text(s, "Research question", { x: M + 0.4, y: 2.85, w: 3.9, h: 0.4, fontSize: 14, bold: true, color: C.accent1 });
  text(s, "Where and when do crashes reported in Khmer news cluster, how much of the real burden does that coverage capture, and how does Cambodia compare with ASEAN?",
    { x: M + 0.4, y: 3.3, w: 3.9, h: 2.9, fontSize: 18, color: C.background1, valign: "top" });
  const hyps = [
    [md.MdPlace, "H1a", "Crashes reported outside Phnom Penh are more often fatal", "One-sided two-proportion z-test"],
    [md.MdPeople, "H1b", "The capital is over-reported for its population", "Chi-square against population shares"],
    [md.MdPublic, "H2", "Cambodia's road death rate rose 2000–2019 while most ASEAN members' fell", "Count of members whose WHO rate fell"],
  ];
  for (let i = 0; i < hyps.length; i++) {
    const [Ic, tag, claim, test] = hyps[i];
    const y = 1.5 + i * 1.75;
    card(s, 5.7, y, 7.03, 1.5, `${tag} card`);
    await iconCircle(s, Ic, 5.95, y + 0.4, 0.7, `${tag} icon`);
    text(s, tag, { x: 6.95, y: y + 0.2, w: 1, h: 0.35, fontSize: 14, bold: true, color: C.accent2 });
    text(s, claim, { x: 6.95, y: y + 0.52, w: 5.5, h: 0.55, fontSize: 16, bold: true });
    text(s, `Test: ${test}`, { x: 6.95, y: y + 1.07, w: 5.5, h: 0.3, fontSize: 13, color: C.text2 });
  }
  s.addNotes("We wrote the topic like the brief's ten topics: one question and hypotheses that could be rejected. " +
    "H1a and H1b are spatial and use our own crash data. H2 is temporal and comparative and uses World Bank data. Each has a named test, chosen before we looked at the result.");

  // 3. Data sources -----------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Question and data" });
  s.addText("Four sources joined on province code and year", { placeholder: "title" });
  const sources = [
    [md.MdNewspaper, "Khmer news", `${fmt(D.n_raw)} articles → ${fmt(D.n_ready)} distinct crashes`, "Text is copyrighted: only extracted fields published"],
    [md.MdMap, "ODC census 2019", "25 provinces: population, households, area, polygons", "CC BY-SA · pulled via GeoServer + CKAN API"],
    [md.MdPublic, "World Bank", "11 ASEAN members, road deaths per 100k, population, GDP", "CC BY 4.0 · pulled via API"],
    [md.MdFactCheck, "Official totals", `Crashes, deaths, injured ${D.coverage.years[0]}–${String(D.coverage.years.at(-1)).slice(2)}: NRSC annual figures`,
      "Government releases · one ministry or state-media page per year"],
  ];
  const cw = 2.85, gap = 0.233;
  for (let i = 0; i < sources.length; i++) {
    const [Ic, name, what, lic] = sources[i];
    const x = M + i * (cw + gap);
    card(s, x, 1.5, cw, 3.0, `${name} card`);
    await iconCircle(s, Ic, x + 0.3, 1.8, 0.7, `${name} icon`);
    text(s, name, { x: x + 0.3, y: 2.65, w: cw - 0.6, h: 0.4, fontSize: 18, bold: true });
    text(s, what, { x: x + 0.3, y: 3.1, w: cw - 0.6, h: 0.75, fontSize: 14 });
    text(s, lic, { x: x + 0.3, y: 3.85, w: cw - 0.6, h: 0.55, fontSize: 12, color: C.text2 });
  }
  s.addShape(pres.shapes.RIGHT_ARROW, { x: 6.27, y: 4.7, w: 0.8, h: 0.5, rotate: 90, fill: { color: C.accent4 }, line: { type: "none" },
    objectName: "flow arrow" });
  card(s, M, 5.45, W - 2 * M, 1.25, "join summary card", C.text1);
  const joins = [[fmt(D.n_ready - 20), "crashes matched to a province code"], ["20", "crashes with no province, kept off the map"],
    ["3", "census spellings matched by province code"], ["6", "joins logged with row counts before and after"]];
  joins.forEach(([n, l], i) => {
    const x = M + 0.3 + i * 2.98;
    text(s, n, { x, y: 5.6, w: 0.85, h: 0.9, fontSize: 30, bold: true, color: C.accent1, valign: "middle" });
    text(s, l, { x: x + 0.85, y: 5.6, w: 1.95, h: 0.9, fontSize: 13, color: C.background1, valign: "middle" });
  });
  s.addNotes("Week 9, data integration. Every source is matched on the official province code or on year. " +
    "The census layer gives both population and real boundaries. Three province names differ between the census and the news, so we built a name-matching table keyed on the code. " +
    "Twenty crashes name no province; we keep them in the totals but not on the map. Every join is logged on the data quality page with row counts before and after.");

  // 4. Portal requirements ---------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Question and data" });
  s.addText("The portal does the eight things the brief asks", { placeholder: "title" });
  const reqs = [
    [md.MdCloudQueue, "Live on the web", "Streamlit app, no login"],
    [md.MdUploadFile, "Accepts uploads", "Checks columns, types, units; lists rejected rows and why"],
    [md.MdSync, "Fetches on its own", "Weekly GitHub Actions job + Refresh button; every pull logged"],
    [md.MdMap, "Map", "Rates per 100k person-years, quantile breaks in the legend"],
    [md.MdTimeline, "Over time", "Trend, season, change on a year earlier, forecast vs naive"],
    [md.MdLink, "Linked views", "Click a province to filter the chart; the period re-colours the map"],
    [md.MdFactCheck, "Honest data page", "Licences, retrieval dates, missing share, outliers"],
    [md.MdLightbulb, "Findings page", "Five findings, each with a number and its chart"],
  ];
  const gw = 2.85, gh = 2.35;
  for (let i = 0; i < reqs.length; i++) {
    const [Ic, name, desc] = reqs[i];
    const x = M + (i % 4) * (gw + 0.233), y = 1.5 + Math.floor(i / 4) * (gh + 0.3);
    card(s, x, y, gw, gh, `${name} card`);
    await iconCircle(s, Ic, x + 0.3, y + 0.3, 0.62, `${name} icon`);
    text(s, name, { x: x + 0.3, y: y + 1.05, w: gw - 0.6, h: 0.4, fontSize: 17, bold: true });
    text(s, desc, { x: x + 0.3, y: y + 1.45, w: gw - 0.6, h: 0.8, fontSize: 14, color: C.text2, valign: "top" });
  }
  s.addNotes("These are the brief's eight requirements, and where each lives in the portal. Clicking a province on the map filters the time chart; moving the period slider re-colours the map. " +
    "Uploads go through the checks in src/validate.py, and the automatic pulls are logged in data/fetch_log.csv. We can show any of these live.");

  // 5. Finding: fatal share --------------------------------------------------------------
  pres.addSection({ title: "Findings" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Findings" });
  s.addText(`Crashes outside the capital are ${h1a.ratio.toFixed(1)}× as often fatal`, { placeholder: "title" });
  stat(s, pct(h1a.fatal_share_outside), `of reported crashes outside Phnom Penh were fatal (n = ${h1a.n_outside})`, M, 1.6, 4.2, C.accent2, 66);
  stat(s, pct(h1a.fatal_share_inside), `inside the capital (n = ${h1a.n_inside})`, M, 3.55, 4.2, C.text1, 66);
  card(s, M, 5.55, 4.2, 1.1, "test result card");
  text(s, [{ text: "H1a not rejected  ", options: { bold: true, color: C.accent2 } },
    { text: `z = ${h1a.z.toFixed(1)}, p < 0.001` }], { x: M + 0.25, y: 5.6, w: 3.8, h: 1.0, fontSize: 16, valign: "middle" });
  s.addChart(pres.charts.BAR, [{ name: "Fatal share", labels: D.road.type, values: D.road.fatal }], chartBase({
    x: 5.3, y: 1.45, w: 7.43, h: 5.1, barDir: "bar", chartColors: [HEX.accent3], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: '0"%"', valAxisMaxVal: 70, valAxisMinVal: 0, valAxisLabelFormatCode: '0"%"', showLegend: false,
    title: "Fatal share of reported crashes by road type, 2018–2024", barGapWidthPct: 60,
  }));
  s.addNotes("Week 12: the title states the finding. Of reported crashes with a known outcome, 55% outside Phnom Penh were fatal against 24% inside: 2.3 times as often. " +
    "The z-test gives z = 8.2, so H1a survives. Road type tells the same story: national roads 56%, city streets 22%. " +
    "Caveat: the news picks which crashes to report. A minor crash in a province may never be written up, which inflates the provincial fatal share.");

  // 6. Finding: coverage -----------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Findings" });
  s.addText(`The capital has ${Math.round(h1b.capital_report_share)}% of reports but ${Math.round(h1b.capital_population_share)}% of people`,
    { placeholder: "title" });
  s.addChart(pres.charts.BAR, [
    { name: "Share of reported crashes", labels: D.top.prov, values: D.top.report },
    { name: "Share of population (census 2019)", labels: D.top.prov, values: D.top.pop },
  ], chartBase({
    x: M, y: 1.45, w: 7.9, h: 5.2, barDir: "bar", barGrouping: "clustered", chartColors: [HEX.accent2, HEX.accent6],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', valAxisLabelFormatCode: '0"%"', valAxisMaxVal: 65, valAxisMinVal: 0, valAxisHidden: true,
    catAxisOrientation: "maxMin", showLegend: true, legendPos: "b", title: "The eight most-reported provinces, 2018–2024", barGapWidthPct: 50,
  }));
  stat(s, `${h1b.rate_ratio.toFixed(1)}×`, "more reports per resident in Phnom Penh than in the rest of the country", 9.0, 1.6, 3.73, C.accent2, 66);
  card(s, 9.0, 3.75, 3.73, 1.1, "test result card");
  text(s, [{ text: "H1b not rejected", options: { bold: true, color: C.accent2, breakLine: true } }, { text: "Chi-square test, p < 0.001" }],
    { x: 9.25, y: 3.8, w: 3.4, h: 1.0, fontSize: 16, valign: "middle" });
  text(s, "So the map of reports is a map of where journalists work. That is why we shade it by rate per resident and never by raw count.",
    { x: 9.0, y: 5.1, w: 3.73, h: 1.5, fontSize: 15, color: C.text2, valign: "top" });
  s.addNotes("Week 4, normalisation. Phnom Penh holds 56% of reported crashes but only 15% of the population, so it is reported 7.5 times as often per resident. " +
    "A chi-square test against population shares rejects proportional coverage, so H1b survives. " +
    "That is the reason every map uses rates per 100,000 person-years, and the reason we read the map as coverage, not risk.");

  // 7. Finding: coverage of official deaths ------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Findings" });
  s.addText(`The news sees about ${pct(covShare)} of official road deaths`, { placeholder: "title" });
  stat(s, pct(covShare), `of officially counted deaths appear in our news sample (${D.coverage.years[0]}–${D.coverage.years.at(-1)})`, M, 1.6, 4.4, C.accent2, 80);
  card(s, M, 3.9, 4.4, 2.75, "caveat card");
  await iconCircle(s, md.MdWarning, M + 0.3, 4.15, 0.6, "warning icon");
  text(s, "The official figures are the National Road Safety Committee's annual counts, taken from ministry and state-media releases (one page per year). WHO's model puts 2021 deaths near 3,000, twice the national count.",
    { x: M + 1.1, y: 4.1, w: 3.1, h: 2.4, fontSize: 14, valign: "top" });
  s.addChart(pres.charts.BAR, [
    { name: "Deaths in our news sample", labels: D.coverage.years.map(String), values: D.coverage.news },
    { name: "Official deaths", labels: D.coverage.years.map(String), values: D.coverage.official },
  ], chartBase({
    x: 5.4, y: 1.45, w: 7.33, h: 5.2, barDir: "col", barGrouping: "clustered", chartColors: [HEX.accent2, HEX.accent6],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0", valAxisLabelFormatCode: "#,##0", valAxisMaxVal: 2000,
    showLegend: true, legendPos: "b", title: "Road deaths per year: news sample against official totals", barGapWidthPct: 70,
  }));
  s.addNotes(`This is the most important limit on everything else. In ${D.coverage.years[0]} to ${D.coverage.years.at(-1)} our news sample recorded ` +
    `${fmt(D.coverage.news.reduce((a, b) => a + b, 0))} deaths against ${fmt(D.coverage.official.reduce((a, b) => a + b, 0))} counted by the National Road Safety Committee, about ${pct(covShare)}. ` +
    "We show this gap instead of hiding it. Each year's official number is typed in from a ministry or state-media page, which is named in official_totals.csv and on the data quality page; " +
    "the committee's own report is not online, and WHO's model puts the true toll at about twice the official count.");

  // 8. Finding: ASEAN --------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Findings" });
  s.addText(`Cambodia's road deaths rose as ${h2.others_fell} of ${h2.others} neighbours' fell`, { placeholder: "title" });
  const khm = D.asean.iso.map((i, k) => (i === "KHM" ? D.asean.change[k] : 0));
  const others = D.asean.iso.map((i, k) => (i === "KHM" ? 0 : D.asean.change[k]));
  s.addChart(pres.charts.BAR, [
    { name: "Cambodia", labels: D.asean.countries, values: khm },
    { name: "Other ASEAN members", labels: D.asean.countries, values: others },
  ], chartBase({
    x: M, y: 1.45, w: 7.9, h: 5.2, barDir: "bar", barGrouping: "stacked", chartColors: [HEX.accent2, HEX.accent4],
    showValue: false, catAxisLabelPos: "low",
    valAxisLabelFormatCode: "+0;-0;0", catAxisOrientation: "minMax", showLegend: true, legendPos: "b",
    title: "Change in road deaths per 100,000, 2000 to 2019 (WHO estimate)", barGapWidthPct: 45,
  }));
  stat(s, h2.khm_rate.toFixed(1), "road deaths per 100,000 in Cambodia in 2019, up 1.7 since 2000", 9.0, 1.6, 3.73, C.accent2, 66);
  stat(s, `${h2.khm_rank} of ${h2.members}`, "Cambodia's rank in ASEAN (1 = highest rate)", 9.0, 3.45, 3.73, C.text1, 54);
  card(s, 9.0, 5.45, 3.73, 1.2, "test result card");
  text(s, [{ text: "H2 not rejected  ", options: { bold: true, color: C.accent2 } }, { text: "WHO figures are modelled estimates" }],
    { x: 9.25, y: 5.5, w: 3.4, h: 1.1, fontSize: 15, valign: "middle" });
  s.addNotes("The ASEAN map in the portal shows this spatially. Between 2000 and 2019 Cambodia's WHO-modelled rate rose by 1.7 to 19.6 per 100,000, while 7 of the other 10 members' rates fell. " +
    "Cambodia ranks 5th of 11. H2 survives. Caveat: these are modelled estimates, and their quality differs between countries, so we say that on the chart.");

  // 9. Time series -----------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Findings" });
  s.addText("Monthly reports track collection, not the roads", { placeholder: "title" });
  const flaggedSet = new Set(fc.flagged_months.map((m) => m.replace(/(\w{3}) 20(\d\d)/, "$1 $2")));
  const monthLabels = D.monthly.labels.map((l) => (l.startsWith("Jan") ? "20" + l.slice(-2) : ""));
  const flaggedVals = D.monthly.labels.map((l, i) => (flaggedSet.has(l) ? D.monthly.values[i] : 0));
  s.addChart([
    { type: pres.charts.BAR, data: [{ name: "Flagged outlier month", labels: monthLabels, values: flaggedVals }],
      options: { chartColors: [HEX.accent1], barGapWidthPct: 20 } },
    { type: pres.charts.LINE, data: [{ name: "Reported crashes per month", labels: monthLabels, values: D.monthly.values }],
      options: { chartColors: [HEX.accent3], lineSize: 2, lineDataSymbol: "none" } },
  ], chartBase({
    x: M, y: 1.45, w: 7.4, h: 3.6, showLegend: true, legendPos: "b", catAxisLabelFrequency: 1, valAxisMinVal: 0,
    title: `Crashes per month: ${fc.flagged} of ${fc.months} months flagged`, catAxisLabelRotate: 0,
  }));
  s.addChart(pres.charts.LINE, [
    { name: "Recorded", labels: fc.test_labels, values: fc.actual },
    { name: "Holt-Winters", labels: fc.test_labels, values: fc.model },
    { name: "Same month last year", labels: fc.test_labels, values: fc.naive },
  ], chartBase({
    x: 8.2, y: 1.45, w: 4.53, h: 3.6, chartColors: [HEX.accent3, HEX.accent2, HEX.accent4], lineSize: 2, lineDataSymbolSize: 5,
    showLegend: true, legendPos: "b", valAxisMinVal: 0, title: "Held-out 2024: forecast against naive",
  }));
  const tsStats = [[fc.mae_model.toFixed(1), "Forecast error (MAE, reports per month)"], [fc.mae_naive.toFixed(1), "Naive error: same month last year"],
    [`${Math.round((1 - fc.mae_model / fc.mae_naive) * 100)}%`, "Better than naive, but MASE is " + fc.mase.toFixed(2)]];
  tsStats.forEach(([v, l], i) => {
    const x = M + i * 4.1;
    card(s, x, 5.3, 3.85, 1.35, `time stat ${i}`);
    text(s, v, { x: x + 0.25, y: 5.35, w: 1.5, h: 1.25, fontSize: 32, bold: true, color: i === 0 ? C.accent2 : C.text1, valign: "middle" });
    text(s, l, { x: x + 1.75, y: 5.35, w: 1.95, h: 1.25, fontSize: 13, color: C.text2, valign: "middle" });
  });
  s.addNotes("Week 11, time series. We put every crash in the month it happened, separated trend and season with STL, trained to December 2023 and scored 2024 once. " +
    "Holt-Winters beats 'same month last year' by 11%: an error of 10.8 against 12.2 reports a month. But week 3 flags 8 of 84 months as outliers, and every flagged month matches a batch of article collection. " +
    "So the honest conclusion is that this series measures when we collected news, and neither forecast says how many crashes will happen.");

  // 10. Rare event -----------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Findings" });
  s.addText(`A rare-event rule catches ${pct(r.test_recall)} of multi-fatality crashes`, { placeholder: "title" });
  const rs = [[`${(r.base_rate_test * 100).toFixed(1)}%`, "Base rate: crashes with 2+ deaths in 2024"], [r.test_recall.toFixed(2), "Recall: share of them we flag"],
    [r.test_precision.toFixed(2), "Precision: share of flags that are right"], [r.threshold.toFixed(2), "Threshold, from a 5:1 miss-to-false-alarm cost"]];
  rs.forEach(([v, l], i) => {
    const x = M + i * 3.08;
    card(s, x, 1.5, 2.85, 1.9, `rare stat ${i}`);
    text(s, v, { x: x + 0.25, y: 1.6, w: 2.4, h: 0.9, fontSize: 40, bold: true, color: i === 1 ? C.accent2 : C.text1, valign: "bottom" });
    text(s, l, { x: x + 0.25, y: 2.55, w: 2.4, h: 0.75, fontSize: 14, color: C.text2, valign: "top" });
  });
  const steps = ["One-hot encoder + scaler", "Logistic regression with class weights", "5-fold CV on 2018–2023", "2024 scored once"];
  steps.forEach((t, i) => {
    const x = M + i * 3.08;
    card(s, x, 3.75, 2.55, 0.95, `pipeline step ${i}`, C.text1);
    text(s, t, { x: x + 0.2, y: 3.75, w: 2.15, h: 0.95, fontSize: 14, bold: true, color: C.background1, valign: "middle" });
    if (i < steps.length - 1) {
      s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.6, y: 4.08, w: 0.42, h: 0.3, fill: { color: C.accent4 }, line: { type: "none" },
        objectName: `pipeline arrow ${i}` });
    }
  });
  card(s, M, 5.0, 6.0, 1.65, "accuracy card");
  text(s, [{ text: "Why not accuracy? ", options: { bold: true } },
    { text: `Never flagging anything scores ${pct(r.accuracy_if_always_no)} accuracy and finds none of the ${r.positives_test} crashes. Our rule scores ${pct(r.test_accuracy)}, yet finds ${Math.round(r.test_recall * r.positives_test)}.` }],
    { x: M + 0.3, y: 5.1, w: 5.4, h: 1.45, fontSize: 15, valign: "middle" });
  card(s, 6.85, 5.0, 5.88, 1.65, "fairness card");
  await iconCircle(s, md.MdBalance, 7.1, 5.5, 0.62, "fairness icon");
  text(s, [{ text: "Fairness check: ", options: { bold: true, color: C.accent2 } },
    { text: `the rule flags ${pct(r.flag_rate_phnom_penh)} of Phnom Penh crashes and ${pct(r.flag_rate_other)} elsewhere. It treats the capital differently.` }],
    { x: 7.95, y: 5.1, w: 4.55, h: 1.45, fontSize: 15, valign: "middle" });
  s.addNotes("Weeks 10 and 13. The rare event is a crash with two or more deaths, 14.4% of 2024 crashes. Everything fitted sits in one pipeline, cross-validated on 2018 to 2023, and 2024 is used once. " +
    "Oversampling inside the folds did no better than class weights, so we kept class weights. A miss costs five false alarms, which sets the threshold at 0.54. " +
    "Recall is 0.73 and precision 0.35. Accuracy would mislead: never flagging scores 86%. And the rule flags none of the Phnom Penh crashes, which we report as an ethics problem.");

  // 11. Course weeks ---------------------------------------------------------------------
  pres.addSection({ title: "Methods and ethics" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Methods and ethics" });
  s.addText("Every course week is in the project", { placeholder: "title" });
  const weeks = [
    ["1", "Pipeline", `${fmt(D.n_raw)} rows → ${fmt(D.n_ready)} crashes; data dictionary`],
    ["2", "Missing values", "Province 2.5% missing; times kept as 'Unknown'"],
    ["3", "Outliers", `${fc.flagged} of ${fc.months} months flagged, none deleted`],
    ["4", "Normalisation", "Per 100k person-years; StandardScaler"],
    ["5", "Encoding", `Province → official code; one-hot adds ${Object.values(r.encoder_widths).reduce((a, b) => a + b, 0)} columns`],
    ["6", "Features", "Rates, year-on-year, rolling share, season"],
    ["8", "Feature selection", `Rule drops deaths per 100k (rho ${D.corr_rule.rho.toFixed(2)}); PC1 keeps ${pct(D.pca1)}`],
    ["9", "Integration", "4 sources, 6 joins logged, name table"],
    ["10", "Imbalance", `Base rate ${(r.base_rate_test * 100).toFixed(1)}%, cost threshold ${r.threshold.toFixed(2)}`],
    ["11", "Time series", `STL; split at 2024; MAE ${fc.mae_model.toFixed(1)} vs ${fc.mae_naive.toFixed(1)}`],
    ["12", "Visualisation", "Titles state findings; class breaks stated"],
    ["13", "One pipeline", "5-fold CV on training rows; test once"],
    ["14", "Ethics", "No text or sub-province places published"],
    ["7, 15", "Defence", `Restart and Run All; seed 42; ${D.n_tests} tests`],
  ];
  const head = ["Week", "Skill", "Number behind the decision"].map((t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text1 } } }));
  const toRows = (rows) => [head, ...rows.map(([w, k, n], i) => [w, k, n].map((t) => ({ text: t, options: { fill: { color: i % 2 ? C.background1 : C.background2 } } })))];
  const tableOpts = (x) => ({ x, y: 1.45, w: 5.95, colW: [0.8, 1.6, 3.55], fontSize: 13, color: C.text1, valign: "middle", rowH: 0.6,
    border: { type: "none" }, margin: [0.04, 0.1, 0.04, 0.1] });
  s.addTable(toRows(weeks.slice(0, 7)), tableOpts(M));
  s.addTable(toRows(weeks.slice(7)), tableOpts(M + 6.18));
  s.addNotes("The brief asks for every week to appear, with the number that justified each decision. This table is the short version; the Methods page in the portal and the notebook give the full one. " +
    "notebooks/analysis.ipynb restarts and runs with no error and reproduces every number on the findings page.");

  // 11b. Feature selection ----------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Methods and ethics" });
  s.addText("Feature selection: two rules, set before looking", { placeholder: "title" });
  const cr = D.corr_rule;
  const full = D.feature_check[0];
  const groups = D.feature_check.slice(1).sort((a, b) => a.cv_pr_auc - b.cv_pr_auc);
  const carries = groups.filter((g) => g.change < -full.fold_sd);
  const carriesText = carries.map((g) => g.without).join(" and ");
  const carriesSentence = carriesText.charAt(0).toUpperCase() + carriesText.slice(1);
  s.addChart(pres.charts.BAR, [{ name: "CV PR-AUC without the group", labels: groups.map((g) => "without " + g.without),
    values: groups.map((g) => Number(g.cv_pr_auc.toFixed(3))) }], chartBase({
    x: M, y: 1.45, w: 6.55, h: 5.35, barDir: "bar", showLegend: false, showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "0.00", valAxisMinVal: 0, valAxisMaxVal: 0.5, valAxisLabelFormatCode: "0.0", catAxisLabelFontSize: 11,
    chartColors: groups.map((g) => (g.change < -full.fold_sd ? HEX.accent2 : HEX.accent6)),
    title: `CV PR-AUC without each feature group (all features ${full.cv_pr_auc.toFixed(2)}, fold sd ${full.fold_sd.toFixed(2)}); ` +
      `orange bars cost more than one sd`,
  }));
  const rules = [
    [md.MdFilterAlt, "Week 8 · Correlation rule",
      `Of any two province indicators with |rho| ≥ ${cr.limit}, the later-listed one is dropped. ` +
      `Dropped: deaths per 100k (rho ${cr.rho.toFixed(2)} with reports per 100k). ` +
      `PCA on the ${cr.n_kept} kept indicators: PC1 keeps ${pct(D.pca1)} of the variance (${pct(D.pca1_before)} before the rule).`],
    [md.MdRule, "Weeks 10 and 13 · Group-drop rule",
      `Refit the pipeline without each of ${groups.length} feature groups, training years only. Drop a group only if CV PR-AUC ` +
      `improves by more than one fold sd. ${carriesSentence} carry signal; ` +
      `${D.feature_groups_dropped.length ? D.feature_groups_dropped.join(", ") + " dropped" : "nothing qualified, so the model is unchanged"}; 2024 was never used.`],
  ];
  for (let i = 0; i < rules.length; i++) {
    const [Ic, name, desc] = rules[i];
    const x = 7.4, y = 1.45 + i * 2.75, w = W - M - x;
    card(s, x, y, w, 2.55, `${name} card`);
    await iconCircle(s, Ic, x + 0.3, y + 0.3, 0.62, `${name} icon`);
    text(s, name, { x: x + 1.05, y: y + 0.28, w: w - 1.2, h: 0.5, fontSize: 16, bold: true, valign: "middle" });
    text(s, desc, { x: x + 0.3, y: y + 0.95, w: w - 0.6, h: 1.5, fontSize: 14, color: C.text2, valign: "top" });
  }
  s.addNotes("Two feature-selection rules, both fixed before we looked at the data. Week 8: across the eight province indicators, any pair with a Spearman rho of 0.8 or more loses the later-listed one. " +
    `That drops deaths per 100,000, which tracks reports per 100,000 at ${cr.rho.toFixed(2)}; PCA on the seven kept indicators keeps ${pct(D.pca1)} of the variance in PC1, up from ${pct(D.pca1_before)}. ` +
    "Weeks 10 and 13: we refit the rare-event pipeline without each feature group on the training years only, and drop a group only if the model does better without it by more than one fold standard deviation. " +
    `${carriesSentence} carry real signal. No group qualified for dropping, so the model did not change, and we report that as a result: a change inside the noise is not evidence either way. 2024 played no part.`);

  // 12. Ethics ---------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Methods and ethics" });
  s.addText("What the data cannot see", { placeholder: "title" });
  const ethics = [
    [md.MdVisibilityOff, "Who is missing", `About ${pct(covShare)} of official deaths reach our sample. Quiet provinces, crashes with no injury and later hospital deaths are under-counted.`],
    [md.MdPrivacyTip, "Identification risk", "Articles name victims and print plates. We publish no text, district, commune, village or exact time; maps stop at province."],
    [md.MdBalance, "Unequal treatment", `The rare-event rule flags ${pct(r.flag_rate_phnom_penh)} of capital crashes. Used to prioritise checks, it would skip Phnom Penh.`],
    [md.MdCalculate, "Modelled statistics", "WHO road mortality is an estimate. Comparing countries compares their statistics systems as much as their roads."],
  ];
  for (let i = 0; i < ethics.length; i++) {
    const [Ic, name, desc] = ethics[i];
    const x = M + (i % 2) * 6.18, y = 1.5 + Math.floor(i / 2) * 2.6;
    card(s, x, y, 5.95, 2.3, `${name} card`);
    await iconCircle(s, Ic, x + 0.3, y + 0.35, 0.7, `${name} icon`);
    text(s, name, { x: x + 1.25, y: y + 0.3, w: 4.4, h: 0.45, fontSize: 18, bold: true });
    text(s, desc, { x: x + 1.25, y: y + 0.8, w: 4.4, h: 1.35, fontSize: 15, color: C.text2, valign: "top" });
  }
  s.addNotes("Week 14. Four ethical limits. The data misses most deaths. The raw articles identify people, so the public repository holds only extracted fields at province level, and 156 rows also carry copyright notices. " +
    "Our own rule treats Phnom Penh differently. And the ASEAN comparison relies on modelled figures.");

  // 13. Conclusion -----------------------------------------------------------------------
  pres.addSection({ title: "Conclusion" });
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Conclusion" });
  s.addText("Coverage, not risk, is the main signal", { placeholder: "title" });
  const takeaways = [
    [pct(h1a.fatal_share_outside), "of provincial reports are fatal: H1a holds"],
    [`${h1b.rate_ratio.toFixed(1)}×`, "capital over-reporting per resident: H1b holds"],
    [`+${h2.khm_change.toFixed(1)}`, "deaths per 100k since 2000 as most neighbours fell: H2 holds"],
    [pct(covShare), "of official deaths reach the news sample"],
  ];
  takeaways.forEach(([v, l], i) => {
    const y = 1.55 + i * 1.22;
    text(s, v, { x: M, y, w: 1.55, h: 1.0, fontSize: 36, bold: true, color: C.accent1, valign: "middle" });
    text(s, l, { x: M + 1.65, y, w: 4.9, h: 1.0, fontSize: 16, color: C.background1, valign: "middle" });
  });
  card(s, 7.55, 1.55, 5.18, 4.1, "next steps card", C.text2);
  text(s, "Next steps", { x: 7.85, y: 1.8, w: 4.6, h: 0.5, fontSize: 20, bold: true, color: C.accent1 });
  text(s, [
    { text: "Obtain the National Road Safety Committee's full annual reports; only ministry summaries are online", options: { bullet: true, breakLine: true } },
    { text: "Add police and provincial records through the upload page", options: { bullet: true, breakLine: true } },
    { text: "Scrape news daily, so collection batches stop driving the series", options: { bullet: true, breakLine: true } },
    { text: "Re-check the rare-event rule's fairness once Phnom Penh has more positives", options: { bullet: true } },
  ], { x: 7.85, y: 2.4, w: 4.6, h: 3.1, fontSize: 16, color: C.background1, paraSpaceAfter: 12, valign: "top" });
  text(s, "Thank you · questions welcome", { x: M, y: 6.55, w: 6.5, h: 0.4, fontSize: 16, color: C.accent6 });
  s.addNotes(`To close: all three hypotheses survived, but the biggest finding is about the data itself. News coverage is concentrated in the capital and captures about ${pct(covShare)} of deaths. ` +
    "The next steps all improve the source rather than the model: the committee's full reports, more records through the upload page, and daily collection. Thank you.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("written", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
